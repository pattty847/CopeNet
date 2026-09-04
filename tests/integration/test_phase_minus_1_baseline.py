"""Runtime regression tests for idempotency, RPC errors, persistence, and replay."""

from __future__ import annotations

_PROMPTED_TOOL_OPEN = "<copenet:tool>"
_PROMPTED_TOOL_CLOSE = "</copenet:tool>"


def _tool_block(call_json: str) -> str:
    """Wrap a scripted tool call in the delimiters the prompted protocol requires."""
    return f"{_PROMPTED_TOOL_OPEN}\n{call_json}\n{_PROMPTED_TOOL_CLOSE}"


import asyncio
from pathlib import Path

import pytest

from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.host.rpc_dispatch import dispatch_rpc
from copenet.host.rpc_schema import RequestFrame
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
            text=_tool_block('{"tool_id":"shell.exec","arguments":{"command":"pwd"}}'),
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


@pytest.mark.asyncio
async def test_idempotency_cache_scoped_per_session(tmp_path: Path) -> None:
    """Same idempotency_key across two sessions must NOT bleed cached result.

    This guards the regression where the cache key omitted session identity and
    session B received session A's cached result.
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
async def test_transcript_persists_tool_only_runs(tmp_path: Path) -> None:
    """Tool-only assistant turns (no final text) must still be appended to transcript with parts.

    A transcript append gated only on assistant text makes tool-only runs vanish
    and breaks later replay.
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
    # user message + assistant message
    assert len(history) >= 2
    assistant_msgs = [m for m in history if m.get("role") == "assistant"]
    assert assistant_msgs, "tool-only run produced no assistant transcript message"
    # The assistant message must carry structured `parts` so tool history
    # survives transcript replay even when the run had no clean
    # final-text answer. (The `state` field will be "final" whenever any
    # assistant text exists, including a stringified tool-call JSON in the
    # prompted-tool path; the parts presence is what we actually care about.)
    parts = assistant_msgs[-1].get("parts")
    assert parts, "tool-only assistant message has no parts — replay would lose tool history"
    kinds = [p.get("kind") for p in parts]
    assert "tool_call" in kinds, f"expected tool_call in parts, got {kinds}"
    assert "tool_result" in kinds, f"expected tool_result in parts, got {kinds}"


@pytest.mark.asyncio
async def test_dispatch_rpc_returns_invalid_request_on_bad_param(tmp_path: Path) -> None:
    """Malformed params are actionable and do not prevent a later valid request."""
    orchestrator = _build_orchestrator(tmp_path, {"fake": FakeProvider()})
    sent: list[dict] = []

    async def send_json(frame: dict) -> None:
        sent.append(frame)

    # chat.history(limit="lol") → handler calls int("lol") which raises ValueError
    req = RequestFrame(id="req-1", method="chat.history", params={"sessionKey": "alpha", "limit": "lol"})
    await dispatch_rpc(req, send_json, orchestrator, set())

    error_frame = sent[-1]
    assert error_frame["id"] == "req-1"
    assert error_frame["ok"] is False
    assert error_frame["error"]["code"] == "INVALID_REQUEST"
    assert "invalid literal" in error_frame["error"]["message"]
    assert "lol" in error_frame["error"]["message"]

    valid_req = RequestFrame(
        id="req-2",
        method="chat.history",
        params={"sessionKey": "alpha", "limit": 10},
    )
    await dispatch_rpc(valid_req, send_json, orchestrator, set())

    valid_frame = sent[-1]
    assert valid_frame["id"] == "req-2"
    assert valid_frame["ok"] is True
    assert valid_frame["payload"]["messages"] == []


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


@pytest.mark.asyncio
async def test_cross_turn_history_replayed_into_next_turn(tmp_path: Path) -> None:
    """The next provider prompt replays both sides of the prior turn."""
    provider = FakeProvider()
    orchestrator = _build_orchestrator(tmp_path, {"fake": provider})

    prompts_seen: list[str] = []
    original_run = provider.run

    async def capturing_run(prompt, provider_session_id, abort_event, model=None, system_prompt=None):
        prompts_seen.append(prompt)
        async for event in original_run(prompt, provider_session_id, abort_event, model=model, system_prompt=system_prompt):
            yield event

    provider.run = capturing_run  # type: ignore[assignment]

    await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="turn-one question", provider="fake"),
    )
    await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="turn-two question", provider="fake"),
    )

    assert len(prompts_seen) == 2
    second_prompt = prompts_seen[1]
    # Turn 1's user message AND assistant reply ("hello") are replayed.
    assert "turn-one question" in second_prompt
    assert "hello" in second_prompt
    # The live ask is the current request.
    assert "turn-two question" in second_prompt
    assert "Current user request" in second_prompt
    assert "Conversation so far" in second_prompt
    # Turn 1's prompt had no prior history section (first turn).
    assert "Conversation so far" not in prompts_seen[0]
