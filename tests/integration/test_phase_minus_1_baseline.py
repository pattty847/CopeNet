"""Phase -1 characterization + fix tests.

Three groups:
1. Tests that pin the FIXES landed in Phase -1.1, -1.2, -1.3.
2. Baseline tests that pin CURRENT broken behavior (will invert in later phases).

Created per HARNESS_REBUILD_V2.md, Phase -1.5.
"""

from __future__ import annotations

_PROMPTED_TOOL_OPEN = "<copenet:tool>"
_PROMPTED_TOOL_CLOSE = "</copenet:tool>"


def _tool_block(call_json: str) -> str:
    """Wrap a scripted tool call in the delimiters the prompted protocol requires."""
    return f"{_PROMPTED_TOOL_OPEN}\n{call_json}\n{_PROMPTED_TOOL_CLOSE}"


import asyncio
import json
from pathlib import Path

import pytest

from copenet.core.harness import tool_loop as harness_tool_loop
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
    # user message + assistant message
    assert len(history) >= 2
    assistant_msgs = [m for m in history if m.get("role") == "assistant"]
    assert assistant_msgs, "tool-only run produced no assistant transcript message"
    # Phase -1.1 fix: the assistant message must carry structured `parts` so
    # tool history survives transcript replay even when the run had no clean
    # final-text answer. (The `state` field will be "final" whenever any
    # assistant text exists, including a stringified tool-call JSON in the
    # prompted-tool path; the parts presence is what we actually care about.)
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


# -- Group 3: baseline characterization tests (Phase -1.5) ----------------------
#
# These pin the CURRENT broken behavior. They are expected to invert during the
# rebuild — flag them when reviewing diffs:
#
#   * test_tool_loop_caps_at_max_tool_steps:
#       After Phase 0.1 lifts MAX_TOOL_STEPS from 4 → 100, the assertion inverts
#       from "only 4 executed" to "all N executed" (for small N up to 100).
#
#   * test_cross_turn_amnesia_in_provider_prompt:
#       After Phase 1 replaces the synthetic working_set with a real messages[]
#       array, the second turn's provider input should contain turn-1 USER+
#       ASSISTANT messages — not the working_set blob. The assertion inverts to
#       multi-message input.


class CountingPromptedProvider:
    """Provider that emits N tool-call requests across N+1 turns.

    Each request asks for a different file path so the in-policy duplicate-call
    suppressor (`_repeat_response`) never trips. We want this test to be
    bounded purely by MAX_TOOL_STEPS, not by repetition heuristics.
    """

    name = "counting"
    display_name = "Counting"

    def __init__(self, *, total_calls: int) -> None:
        self.total_calls = total_calls
        self.calls_emitted = 0
        self.prompts: list[str] = []

    async def run(self, prompt, provider_session_id, abort_event, model=None, system_prompt=None):
        del abort_event, model, system_prompt
        self.prompts.append(prompt)
        if self.calls_emitted < self.total_calls:
            self.calls_emitted += 1
            text = _tool_block(
                '{"tool_id":"files.read","arguments":{"path":"FILE_'
                + str(self.calls_emitted)
                + '.md"}}'
            )
            yield ProviderEvent(kind="delta", text=text, provider_session_id=provider_session_id or "ps")
            yield ProviderEvent(kind="final")
            return
        yield ProviderEvent(
            kind="delta",
            text=f"All done after {self.total_calls} tool calls.",
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


@pytest.mark.asyncio
async def test_tool_loop_caps_at_max_tool_steps(tmp_path: Path) -> None:
    """Provider keeps requesting tools; loop caps execution at MAX_TOOL_STEPS.

    BASELINE (Phase -1): MAX_TOOL_STEPS=4. Even if the provider would happily
    keep going, the harness stops after the 4th tool execution and returns
    whatever final text exists (or nothing).

    PHASE 0.1 EXPECTED INVERSION: cap rises to 100. With total_calls=5, all
    five tool calls execute and a final assistant message follows.
    """
    # Pre-populate distinct files so each files.read call resolves successfully.
    for i in range(1, 11):
        (tmp_path / f"FILE_{i}.md").write_text(f"contents of FILE_{i}\n", encoding="utf-8")
    provider = CountingPromptedProvider(total_calls=5)
    orchestrator = _build_orchestrator(tmp_path, {"counting": provider})

    result, events = await _collect_events(
        orchestrator,
        ChatSendRequest(
            session_key="alpha",
            message="loop please",
            provider="counting",
            task_prompt_id="full-access",
        ),
    )

    assert result["status"] == "ok"
    tool_executions = [ev for ev in events if ev.get("state") == "tool_result"]
    cap = harness_tool_loop.MAX_TOOL_STEPS
    assert cap in (4, 100), (
        f"unexpected MAX_TOOL_STEPS={cap}; "
        "this test understands both pre-Phase-0 (4) and post-Phase-0 (100) regimes."
    )
    if cap == 4:
        assert len(tool_executions) == 4, (
            f"BASELINE: expected exactly 4 tool calls under MAX_TOOL_STEPS=4, got {len(tool_executions)}"
        )
    else:
        assert len(tool_executions) == 5, (
            f"POST-PHASE-0: expected all 5 tool calls to execute, got {len(tool_executions)}"
        )


@pytest.mark.asyncio
async def test_cross_turn_history_replayed_into_next_turn(tmp_path: Path) -> None:
    """Phase 1 INVERSION of the old amnesia baseline.

    Pre-Phase-1, the working_set blob omitted prior assistant text — the model
    was amnesiac about its own replies. After Phase 1, build_chat_messages
    replays the full transcript: turn 2's outgoing prompt contains BOTH turn 1's
    user message AND turn 1's assistant reply, under a "Conversation so far"
    history section, with the live ask under "Current user request".
    """
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
