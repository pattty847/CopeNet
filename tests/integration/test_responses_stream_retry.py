"""A provider stream that dies before producing anything is re-requested once; one that dies after showing text is not."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

from copenet.core.orchestrator import Orchestrator
from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent
from responses_fake import ScriptedResponsesProvider


class DroppingProvider(ScriptedResponsesProvider):
    """Drops the stream on the given 1-based call numbers, before or after a partial delta."""

    def __init__(self, *args: Any, drop_calls: set[int], after_partial_text: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.drop_calls = drop_calls
        self.after_partial_text = after_partial_text
        self.stream_calls = 0

    async def stream_responses(self, **kwargs: Any) -> AsyncIterator[ProviderEvent]:  # type: ignore[override]
        self.stream_calls += 1
        if self.stream_calls in self.drop_calls:
            self.messages.append([dict(item) for item in kwargs["messages"]])  # record what the dropped attempt saw
            if self.after_partial_text:
                yield ProviderEvent(kind="delta", text="Partial answer that already reached the operator")
            raise RuntimeError("openai-codex stream ended incomplete")
        async for event in super().stream_responses(**kwargs):
            yield event


def _orchestrator(tmp_path: Path, provider: ScriptedResponsesProvider) -> Orchestrator:
    return Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={provider.name: provider},
    )


async def _send(orchestrator: Orchestrator, provider: ScriptedResponsesProvider, workspace: Path, run_id: str) -> dict:
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    result = await orchestrator.send_chat(
        ChatSendRequest(session_key="retry-session", message="Read app.py then answer", idempotency_key=run_id, provider=provider.name, task_prompt_id="full-access", workspace_root=str(workspace)),
        emit=emit,
    )
    return {"result": result, "events": events}


def _trace_rows(tmp_path: Path, run_id: str) -> list[dict]:
    return [json.loads(line) for line in (tmp_path / "logs" / "runs" / f"{run_id}.jsonl").read_text().splitlines() if line.strip()]


@pytest.mark.asyncio
async def test_a_stream_that_drops_before_any_output_is_retried_and_the_turn_completes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from copenet.core.harness import tool_loop_responses

    monkeypatch.setattr(tool_loop_responses, "RESPONSES_STREAM_RETRY_DELAY_SEC", 0.0)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    # call 1: read; call 2: drops; call 3 (the retry of step 2): the final answer
    provider = DroppingProvider(outputs=['{"tool_id": "files.read", "arguments": {"path": "app.py"}}', "VALUE is 1."], drop_calls={2})
    orchestrator = _orchestrator(tmp_path, provider)

    outcome = await _send(orchestrator, provider, workspace, "run-1")

    assert outcome["result"]["status"] == "ok", outcome["result"]
    assert provider.stream_calls == 3
    final = next(e for e in outcome["events"] if e.get("state") == "final")
    assert final["message"]["content"] == "VALUE is 1."
    retries = [row for row in _trace_rows(tmp_path, "run-1") if row["event"] == "provider_stream_retry"]
    assert len(retries) == 1 and retries[0]["payload"]["step"] == 2 and retries[0]["payload"]["attempt"] == 1
    # the array the retry re-sent is the same one the dropped attempt saw
    assert provider.messages[1] == provider.messages[2]


@pytest.mark.asyncio
async def test_a_stream_that_drops_after_showing_text_is_not_retried(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from copenet.core.harness import tool_loop_responses

    monkeypatch.setattr(tool_loop_responses, "RESPONSES_STREAM_RETRY_DELAY_SEC", 0.0)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    provider = DroppingProvider(outputs=["never reached"], drop_calls={1}, after_partial_text=True)
    orchestrator = _orchestrator(tmp_path, provider)

    outcome = await _send(orchestrator, provider, workspace, "run-2")

    assert outcome["result"]["status"] != "ok"
    assert provider.stream_calls == 1
    assert not [row for row in _trace_rows(tmp_path, "run-2") if row["event"] == "provider_stream_retry"]


@pytest.mark.asyncio
async def test_two_drops_in_a_row_surface_the_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from copenet.core.harness import tool_loop_responses

    monkeypatch.setattr(tool_loop_responses, "RESPONSES_STREAM_RETRY_DELAY_SEC", 0.0)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    provider = DroppingProvider(outputs=["never reached"], drop_calls={1, 2})
    orchestrator = _orchestrator(tmp_path, provider)

    outcome = await _send(orchestrator, provider, workspace, "run-3")

    assert outcome["result"]["status"] != "ok"
    assert provider.stream_calls == 2
    assert len([row for row in _trace_rows(tmp_path, "run-3") if row["event"] == "provider_stream_retry"]) == 1
    await asyncio.sleep(0)
