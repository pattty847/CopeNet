"""Tests for core/coordination/lane_runner.py — the shared dual-lane primitive."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from copenet.core.coordination import LaneTurnSpec, create_lane_sessions, run_lane_turn, select_lane_updates
from copenet.core.runtime.runs import RunRecord, RunStore
from copenet.core.sessions import SessionStore


class FakeOrchestrator:
    """Mirrors the real split: the streaming `emit` callback only ever carries
    lightweight `toolExecution` receipts (runtime.py never re-emits the full
    `toolResult` body); the full body only lands on the completed RunRecord,
    which `run_lane_turn` reads back via `_run_store.get()` after `send_chat`
    returns — exactly like the real orchestrator."""

    def __init__(self, root: Path) -> None:
        self._session_store = SessionStore(path=root / "index.json")
        self._run_store = RunStore(root_dir=root / "runs")
        self.received_requests: list[Any] = []
        self.scripted_events: list[dict[str, Any]] = [
            {"state": "delta", "message": {"content": "thinking..."}},
            {
                "state": "tool_result",
                "toolExecution": {"toolId": "web.fetch", "ok": True, "summary": "Fetched page", "preview": None},
            },
            {"state": "final", "message": {"content": "Here is what I found."}},
        ]
        self.scripted_tool_results: list[dict[str, Any]] = [
            {"toolId": "web.fetch", "body": {"url": "https://example.com", "title": "Example", "text": "x" * 50, "excerpt": "x" * 50, "wordCount": 50}}
        ]
        self.run_id = "run-123"

    async def send_chat(self, request, emit) -> dict[str, Any]:
        self.received_requests.append(request)
        for event in self.scripted_events:
            await emit(event)
        self._run_store.create(
            RunRecord(
                run_id=self.run_id,
                session_key=request.session_key,
                provider=request.provider,
                model=request.model,
                status="ok",
                user_message=request.message,
                tool_execution_mode="responses",
                will_attempt_tool_loop=True,
                tool_results=self.scripted_tool_results,
            )
        )
        return {"runId": self.run_id}


def test_select_lane_updates_excludes_own_events_and_pre_cursor_events() -> None:
    events = [
        {"seq": 1, "author": "gatherer", "kind": "note"},
        {"seq": 2, "author": "analyst_a", "kind": "memo"},
        {"seq": 3, "author": "analyst_b", "kind": "memo"},
    ]
    updates, delivered_through = select_lane_updates(events, cursor=1, participant_id="analyst_a")
    assert delivered_through == 3
    assert [event["seq"] for event in updates] == [3]  # excludes seq<=cursor and own-authored events


def test_create_lane_sessions_rolls_back_all_on_partial_failure(tmp_path: Path) -> None:
    orchestrator = FakeOrchestrator(tmp_path)
    # Pre-occupy the session_key the second participant would need, so the
    # second create_session call inside create_lane_sessions fails partway
    # through and the first (already-created) lane must be rolled back.
    orchestrator._session_store.create_session(
        session_key="run-1-lane-taken", provider="openai-codex", session_type="research_lane"
    )
    with pytest.raises(ValueError):
        create_lane_sessions(
            orchestrator,
            parent_key="run-1",
            session_type="research_lane",
            title_prefix="Test",
            participant_specs={
                "ok": {"provider": "openai-codex", "model": "gpt-5.5"},
                "taken": {"provider": "openai-codex", "model": "gpt-5.5"},
            },
            workspace_root=None,
        )
    # the "ok" lane that succeeded before "taken" collided must be archived, not left dangling
    ok_entry = orchestrator._session_store.get("run-1-lane-ok")
    assert ok_entry is not None
    assert ok_entry.archived is True


@pytest.mark.asyncio
async def test_run_lane_turn_captures_full_tool_results_and_lightweight_receipts(tmp_path: Path) -> None:
    orchestrator = FakeOrchestrator(tmp_path)
    orchestrator._session_store.create_session(
        session_key="lane-1", provider="openai-codex", model="gpt-5.5", session_type="research_lane"
    )

    result = await run_lane_turn(
        orchestrator,
        LaneTurnSpec(session_key="lane-1", provider="openai-codex", model="gpt-5.5", prompt="go research"),
    )

    assert result["content"] == "Here is what I found."
    assert result["toolCallCount"] == 1
    assert result["toolReceipts"][0]["toolId"] == "web.fetch"
    assert "body" not in result["toolReceipts"][0]  # receipts stay lightweight
    assert result["toolResults"][0]["body"]["url"] == "https://example.com"  # full body reaches the caller
    assert orchestrator.received_requests[0].session_key == "lane-1"


@pytest.mark.asyncio
async def test_run_lane_turn_raises_when_lane_returns_no_content(tmp_path: Path) -> None:
    orchestrator = FakeOrchestrator(tmp_path)
    orchestrator.scripted_events = [{"state": "final", "message": {"content": ""}}]
    orchestrator._session_store.create_session(session_key="lane-2", provider="openai-codex", session_type="research_lane")

    with pytest.raises(RuntimeError, match="no assistant content"):
        await run_lane_turn(
            orchestrator, LaneTurnSpec(session_key="lane-2", provider="openai-codex", model=None, prompt="go")
        )
