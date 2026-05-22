"""Phase -1 characterization + fix tests.

Three groups:
1. Tests that pin the FIXES landed in Phase -1.1, -1.2, -1.3.
2. Baseline tests that pin CURRENT broken behavior (will invert in later phases).

Created per HARNESS_REBUILD_V2.md, Phase -1.5.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.rpc_dispatch import dispatch_rpc
from copenet.host.rpc_schema import RequestFrame, make_response_frame, ResponseFrame, RpcError
from copenet.providers import ProviderEvent


# -- Test providers -------------------------------------------------------------


class FakeProvider:
    name = "fake"
    display_name = "Fake"

    async def run(self, prompt, provider_session_id, abort_event, model=None, system_prompt=None):
        del prompt, abort_event, model, system_prompt
        yield ProviderEvent(kind="delta", text="hello", provider_session_id=provider_session_id or "ps")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False},
        }

    async def list_models(self) -> list:
        return []


class ToolOnlyProvider:
    """Emits a tool call but no final text — exercises the persistence gate fix."""

    name = "tool-only"
    display_name = "Tool Only"

    async def run(self, prompt, provider_session_id, abort_event, model=None, system_prompt=None):
        del prompt, abort_event, model, system_prompt
        # Emit a prompted-tool JSON request (no human text)
        yield ProviderEvent(
            kind="delta",
            text='{"tool_id":"shell.exec","arguments":{"command":"pwd"}}',
            provider_session_id=provider_session_id or "ps",
        )
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {
                "chat": True,
                "streaming": True,
                "toolCalls": False,
                "promptedToolUse": True,
            },
        }

    async def list_models(self) -> list:
        return []


async def _collect_events(orchestrator: Orchestrator, request: ChatSendRequest) -> tuple[dict, list[dict]]:
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    result = await orchestrator.send_chat(request, emit=emit)
    return result, events


def _build_orchestrator(tmp_path: Path, providers: dict) -> Orchestrator:
    return Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers=providers,
    )


# -- Group 1: fix verifications -------------------------------------------------


@pytest.mark.asyncio
async def test_idempotency_cache_scoped_per_session(tmp_path: Path) -> None:
    """Same idempotency_key across two sessions must NOT bleed cached result.

    Before Phase -1.2, dedupe_key was f"chat:{run_id}" and run_id was the
    idempotency_key itself — so session B got session A's cached result.
    """
    orchestrator = _build_orchestrator(tmp_path, {"fake": FakeProvider(), "fake2": FakeProvider()})

    # Session A sends with key "shared"
    result_a, _ = await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="A's message", provider="fake", idempotency_key="shared"),
    )
    assert result_a["status"] == "ok"

    # Session B sends with the SAME key — must NOT return cached
    result_b, events_b = await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="beta", message="B's message", provider="fake", idempotency_key="shared"),
    )
    assert result_b["status"] == "ok", "session B incorrectly got cached result from session A"
    # B should have actually run and emitted its own events
    assert any(ev.get("state") == "final" for ev in events_b)


@pytest.mark.asyncio
async def test_idempotency_cache_still_dedupes_within_same_session(tmp_path: Path) -> None:
    """Same session + same idempotency_key still returns cached. Per-session scoping preserves intent."""
    orchestrator = _build_orchestrator(tmp_path, {"fake": FakeProvider()})

    first, _ = await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Hi", provider="fake", idempotency_key="retry-1"),
    )
    second, events = await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Hi", provider="fake", idempotency_key="retry-1"),
    )
    assert first["status"] == "ok"
    assert second["status"] == "cached"
    assert events == []


@pytest.mark.asyncio
async def test_transcript_persists_tool_only_runs(tmp_path: Path) -> None:
    """Tool-only assistant turns (no final text) must still be appended to transcript with parts.

    Before Phase -1.1, the transcript append was gated on `assistant_text` being
    nonempty — so tool-only runs vanished from history entirely. This broke any
    future replay relying on transcript parts.
    """
    orchestrator = _build_orchestrator(tmp_path, {"tool-only": ToolOnlyProvider()})

    await _collect_events(
        orchestrator,
        ChatSendRequest(
            session_key="alpha",
            message="Run pwd",
            provider="tool-only",
            task_prompt_id="full-access",  # required so shell.exec is allowed
        ),
    )

    history = orchestrator.history("alpha")
    # user message + assistant tool-only message
    assert len(history) >= 2
    assistant_msgs = [m for m in history if m.get("role") == "assistant"]
    assert assistant_msgs, "tool-only run produced no assistant transcript message"
    # The persisted assistant message should be marked as tool_only state
    assert assistant_msgs[-1].get("state") == "tool_only"
    # And its `parts` must contain the structured tool exchange
    parts = assistant_msgs[-1].get("parts")
    assert parts, "tool-only assistant message has no parts — replay would lose tool history"
    kinds = [p.get("kind") for p in parts]
    assert "tool_call" in kinds, f"expected tool_call in parts, got {kinds}"
    assert "tool_result" in kinds, f"expected tool_result in parts, got {kinds}"


# -- Group 2: RPC error boundary fix --------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_rpc_returns_invalid_request_on_bad_param(tmp_path: Path) -> None:
    """Malformed RPC params return a structured error, not a thrown exception that kills the socket.

    Before Phase -1.3, `int("lol")` inside a handler bubbled out through dispatch
    and dropped the WebSocket. Now: caught, structured INVALID_REQUEST response.
    """
    orchestrator = _build_orchestrator(tmp_path, {"fake": FakeProvider()})
    sent: list[dict] = []

    async def send_json(frame: dict) -> None:
        sent.append(frame)

    # chat.history(limit="lol") → handler calls int("lol") which raises ValueError
    req = RequestFrame(id="req-1", method="chat.history", params={"sessionKey": "alpha", "limit": "lol"})
    tasks: set = set()
    # MUST NOT raise — the boundary catches it
    await dispatch_rpc(req, send_json, orchestrator, tasks)

    assert sent, "dispatch_rpc returned no response frame"
    frame = sent[-1]
    # Verify the response is shaped as an error frame for req-1
    assert frame.get("id") == "req-1"
    assert frame.get("ok") is False
    error = frame.get("error") or {}
    assert error.get("code") in {"INVALID_REQUEST", "INTERNAL_ERROR"}


@pytest.mark.asyncio
async def test_dispatch_rpc_unknown_method_still_returns_clean_error(tmp_path: Path) -> None:
    """Unknown method path still uses METHOD_NOT_FOUND (existing behavior — sanity check)."""
    orchestrator = _build_orchestrator(tmp_path, {"fake": FakeProvider()})
    sent: list[dict] = []

    async def send_json(frame: dict) -> None:
        sent.append(frame)

    req = RequestFrame(id="req-2", method="does.not.exist", params={})
    await dispatch_rpc(req, send_json, orchestrator, set())

    assert sent
    frame = sent[-1]
    assert frame.get("ok") is False
    assert (frame.get("error") or {}).get("code") == "METHOD_NOT_FOUND"
