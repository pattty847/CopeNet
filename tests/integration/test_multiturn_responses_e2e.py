"""In-process integration of multi-turn replay through the orchestrator and Responses loop.

This is the strongest integration proof for the rebuild's spine: it drives two
full send_chat turns through a real Orchestrator with a fake Responses provider,
and asserts that turn 2's OUTGOING input[] array — built by build_chat_messages
from the persisted transcript — carries turn 1's user message, the function_call,
the function_call_output WITH THE REAL TOOL OUTPUT (not just a summary), and the
assistant text. It protects message assembly, the Responses loop, transcript
persistence, and replayOutput together.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent


def _fc_event(call_id: str, name: str, arguments: str) -> ProviderEvent:
    return ProviderEvent(
        kind="meta",
        metadata={"responsesFunctionCall": {"id": f"fc_{call_id}", "call_id": call_id, "name": name, "arguments": arguments}},
    )


_COMPLETED = ProviderEvent(kind="meta", metadata={"responsesCompleted": True})


class FakeResponsesProvider:
    """A responses-capable provider that records every input[] it is handed."""

    name = "fake-responses"
    display_name = "Fake Responses"

    def __init__(self, turns: list[list[ProviderEvent]]) -> None:
        self._turns = turns
        self._index = 0
        self.seen_inputs: list[list[dict[str, Any]]] = []

    async def run(self, *args, **kwargs):  # pragma: no cover - responses path must not use run()
        raise AssertionError("responses provider should use stream_responses, not run()")
        yield  # noqa: unreachable

    async def stream_responses(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        model: str | None,
        instructions: str | None,
        prompt_cache_key: str | None,
        reasoning: dict[str, Any] | None,
        parallel_tool_calls: bool,
        abort_event: asyncio.Event,
    ) -> AsyncIterator[ProviderEvent]:
        self.seen_inputs.append([dict(m) for m in messages])
        events = self._turns[min(self._index, len(self._turns) - 1)]
        self._index += 1
        for event in events:
            yield event

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False, "responsesApi": True},
        }

    async def list_models(self) -> list:
        return []


async def _collect(orchestrator: Orchestrator, request: ChatSendRequest) -> list[dict]:
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    await orchestrator.send_chat(request, emit=emit)
    return events


@pytest.mark.asyncio
async def test_two_turn_responses_replay_carries_tool_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    (tmp_path / "foo.txt").write_text("CONFIG_VALUE=42\nsecond line\n", encoding="utf-8")

    provider = FakeResponsesProvider(
        turns=[
            # send_chat #1, stream call #1: ask to read foo.txt
            [_fc_event("call_1", "files.read", '{"path":"foo.txt"}'), _COMPLETED],
            # send_chat #1, stream call #2: finalize with text
            [ProviderEvent(kind="delta", text="foo.txt holds the config."), _COMPLETED],
            # send_chat #2, stream call #1: finalize directly (no tools)
            [ProviderEvent(kind="delta", text="The config value is 42."), _COMPLETED],
        ]
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={"fake-responses": provider},
    )

    # Turn 1 — model reads foo.txt via a native function call.
    events1 = await _collect(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="what's in foo.txt?", provider="fake-responses"),
    )
    assert any(e.get("state") == "tool_result" for e in events1)
    assert any(e.get("state") == "final" for e in events1)

    # Turn 2 — a fresh ask. The provider's input for this turn is what we assert on.
    await _collect(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="what was the config value?", provider="fake-responses"),
    )

    # provider saw 3 stream calls total (2 for turn 1's loop, 1 for turn 2).
    assert len(provider.seen_inputs) == 3
    turn2_input = provider.seen_inputs[2]
    item_types = [item.get("type") or item.get("role") for item in turn2_input]

    # Turn 1's full exchange is replayed into turn 2's input[].
    assert "function_call" in item_types
    assert "function_call_output" in item_types
    # First item is turn 1's user message; last is turn 2's live ask.
    assert turn2_input[0].get("role") == "user"
    assert "foo.txt" in turn2_input[0]["content"][0]["text"]
    assert turn2_input[-1].get("role") == "user"
    assert "config value" in turn2_input[-1]["content"][0]["text"]

    # The function_call_output replays the REAL file contents, not just a summary.
    fco = next(item for item in turn2_input if item.get("type") == "function_call_output")
    assert "CONFIG_VALUE=42" in fco["output"], (
        f"replayed tool output lost the file contents: {fco['output']!r}"
    )

    # function_call and its output share a call_id (so the API can pair them).
    fc = next(item for item in turn2_input if item.get("type") == "function_call")
    assert fc["call_id"] == fco["call_id"]
    # The messages array carries the canonical (dotted) id; the real provider
    # sanitizes it to files_read only at the API boundary (see the
    # _build_responses_payload tests). The fake records what the loop passed.
    assert fc["name"] == "files.read"


@pytest.mark.asyncio
async def test_responses_turn_persists_tool_exchange_to_transcript(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    (tmp_path / "bar.txt").write_text("hello bar", encoding="utf-8")

    provider = FakeResponsesProvider(
        turns=[
            [_fc_event("c1", "files.read", '{"path":"bar.txt"}'), _COMPLETED],
            [ProviderEvent(kind="delta", text="done"), _COMPLETED],
        ]
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={"fake-responses": provider},
    )

    await _collect(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="read bar", provider="fake-responses"),
    )

    history = orchestrator.history("alpha")
    assistant = [m for m in history if m.get("role") == "assistant"][-1]
    parts = assistant.get("parts") or []
    kinds = [p.get("kind") for p in parts]
    assert "tool_call" in kinds
    assert "tool_result" in kinds
    # The persisted tool_result carries the real output for future replay.
    tool_result = next(p for p in parts if p.get("kind") == "tool_result")
    assert "hello bar" in (tool_result["toolExecution"].get("replayOutput") or "")


class ResumingCliProvider:
    """Mimics claude-cli: resumes a server-side thread, records prompts."""

    display_name = "Resuming CLI"

    def __init__(self, name: str) -> None:
        self.name = name
        self.prompts: list[str] = []

    async def run(self, prompt, provider_session_id, abort_event, model=None, system_prompt=None):
        del abort_event, model, system_prompt
        self.prompts.append(prompt)
        # Always surface a (stable) session id so subsequent turns resume.
        yield ProviderEvent(kind="delta", text="ok", provider_session_id=provider_session_id or "cli-session-1")
        yield ProviderEvent(kind="final", provider_session_id=provider_session_id or "cli-session-1")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False, "promptedToolUse": False, "resume": True},
        }

    async def list_models(self) -> list:
        return []


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["claude-cli"])
async def test_resuming_cli_gets_only_new_message_not_full_history(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, provider_name: str
) -> None:
    monkeypatch.setenv("COPNET_WORKDIR", str(tmp_path))
    provider = ResumingCliProvider(provider_name)
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={provider_name: provider},
    )

    await _collect(orchestrator, ChatSendRequest(session_key="a", message="first turn question", provider=provider_name))
    await _collect(orchestrator, ChatSendRequest(session_key="a", message="second turn question", provider=provider_name))

    assert len(provider.prompts) == 2
    # Turn 2 resumes the CLI thread, so it must receive ONLY the new message
    # (the CLI path may wrap it with system instructions, hence containment) —
    # NOT the prior turn re-stated, which would double the CLI's own context.
    assert "second turn question" in provider.prompts[1]
    assert "first turn question" not in provider.prompts[1]
    assert "Conversation so far" not in provider.prompts[1]
