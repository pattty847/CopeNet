"""Phase 2 (HARNESS_REBUILD_V2): native Responses-API tool loop tests.

Drives run_with_responses_tools with a scripted provider that replays the
event vocabulary captured in PASS-7 (output_text.delta, reasoning_summary.delta,
function_call lifecycle via responsesFunctionCall meta, responsesCompleted).
Asserts tools are extracted, executed, and the next request's input[] carries
the function_call + function_call_output items.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

import pytest

from copenet.core.harness import PromptOverlay
from copenet.core.harness.planning import HarnessTurnPlan
from copenet.core.harness.capabilities import ModelCapabilityProfile
from copenet.core.harness.tool_loop import run_with_responses_tools
from copenet.core.tools import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicy,
)
from copenet.providers import ProviderEvent


def _fc(call_id: str, name: str, arguments: dict) -> ProviderEvent:
    return ProviderEvent(
        kind="meta",
        metadata={
            "responsesFunctionCall": {
                "id": f"fc_{call_id}",
                "call_id": call_id,
                "name": name,
                "arguments": json.dumps(arguments),
            }
        },
    )


_COMPLETED = ProviderEvent(kind="meta", metadata={"responsesCompleted": True})


class ScriptedResponsesProvider:
    """Replays a list of event-lists, one per stream_responses invocation.

    Records the `messages` array it was handed on each call so tests can assert
    that function_call / function_call_output items were appended across turns.
    """

    name = "scripted-responses"

    def __init__(self, turns: list[list[ProviderEvent]]) -> None:
        self._turns = turns
        self._index = 0
        self.seen_messages: list[list[dict[str, Any]]] = []
        self.seen_tools: list[list[dict[str, Any]] | None] = []
        self.seen_instructions: list[str | None] = []
        self.seen_cache_keys: list[str | None] = []
        self.seen_reasoning: list[dict[str, Any] | None] = []

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
        self.seen_messages.append([dict(m) for m in messages])
        self.seen_tools.append([dict(t) for t in tools] if tools else None)
        self.seen_instructions.append(instructions)
        self.seen_cache_keys.append(prompt_cache_key)
        self.seen_reasoning.append(dict(reasoning) if reasoning else None)
        events = self._turns[min(self._index, len(self._turns) - 1)]
        self._index += 1
        for event in events:
            yield event

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": "Scripted Responses",
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False, "responsesApi": True},
        }

    async def list_models(self) -> list:
        return []


def _make_plan() -> HarnessTurnPlan:
    tools = [
        ToolDescriptor(
            id="files.read",
            name="Read File",
            description="Read a file.",
            category="repo-read",
            input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
            capabilities=["filesystem", "read"],
            evidence_role="grounding",
            side_effect="read",
        )
    ]
    return HarnessTurnPlan(
        provider="scripted-responses",
        model="gpt-5.5",
        capability_profile=ModelCapabilityProfile(
            provider="scripted-responses", model="gpt-5.5", responses_api=True
        ),
        tools=tools,
        will_attempt_tool_loop=True,
        tool_execution_mode="responses",
    )


def _make_context(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="s1",
        provider_name="scripted-responses",
        model="gpt-5.5",
        session_store=None,  # type: ignore[arg-type]
        transcript_store=None,  # type: ignore[arg-type]
        providers={},
        policy=ToolPolicy(),
        available_tools=[],
        memory_service=None,
        workspace_intel_service=None,
        artifact_store=None,
        task_prompt_id=None,
        run_id="run1",
        trace=None,
    )


async def _drain(stream) -> list[ProviderEvent]:
    return [event async for event in stream]


@pytest.mark.asyncio
async def test_responses_loop_executes_tool_then_finalizes(tmp_path: Path) -> None:
    (tmp_path / "foo.txt").write_text("Hello, world!", encoding="utf-8")

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        assert request.tool_id == "files.read"
        assert request.arguments == {"path": "foo.txt"}
        return ToolExecutionResult(
            tool_id="files.read", ok=True, summary="Read foo.txt", body="Hello, world!"
        )

    provider = ScriptedResponsesProvider(
        turns=[
            # Turn 1: a reasoning blip, then a function_call, then completion.
            [
                ProviderEvent(kind="reasoning_delta", text="thinking about the file"),
                _fc("call_1", "files.read", {"path": "foo.txt"}),
                _COMPLETED,
            ],
            # Turn 2: final assistant text, no function calls.
            [
                ProviderEvent(kind="delta", text="The file says Hello, world!"),
                _COMPLETED,
            ],
        ]
    )

    events = await _drain(
        run_with_responses_tools(
            provider=provider,
            messages=[{"role": "user", "content": [{"type": "input_text", "text": "what's in foo.txt?"}]}],
            abort_event=asyncio.Event(),
            model="gpt-5.5",
            instructions="be helpful",
            plan=_make_plan(),
            tool_executor=tool_executor,
            tool_context=_make_context(tmp_path),
            session_id="s1",
        )
    )

    # Reasoning passed through.
    assert any(e.kind == "reasoning_delta" and e.text == "thinking about the file" for e in events)
    # toolCall + toolExecution meta emitted with matching callId.
    tool_calls = [e for e in events if e.kind == "meta" and e.metadata and e.metadata.get("toolCall")]
    tool_results = [e for e in events if e.kind == "meta" and e.metadata and e.metadata.get("toolExecution")]
    assert len(tool_calls) == 1
    assert tool_calls[0].metadata["toolCall"]["callId"] == "call_1"
    assert len(tool_results) == 1
    assert tool_results[0].metadata["toolExecution"]["callId"] == "call_1"
    # Final assistant text streamed.
    assert any(e.kind == "delta" and e.text == "The file says Hello, world!" for e in events)
    assert events[-1].kind == "final"

    # The SECOND stream_responses call must include the function_call and
    # function_call_output items appended after turn 1.
    assert len(provider.seen_messages) == 2
    second_input = provider.seen_messages[1]
    types = [item.get("type") for item in second_input]
    assert "function_call" in types
    assert "function_call_output" in types
    fc_item = next(i for i in second_input if i.get("type") == "function_call")
    fco_item = next(i for i in second_input if i.get("type") == "function_call_output")
    assert fc_item["call_id"] == "call_1"
    assert fco_item["call_id"] == "call_1"
    # One canonical envelope on every loop: ok/summary/error travel with the body so
    # a policy block or handler error is legible instead of arriving as `{}`.
    envelope = json.loads(fco_item["output"])
    assert envelope["ok"] is True
    assert envelope["summary"] == "Read foo.txt"
    assert envelope["body"] == "Hello, world!"
    # prompt_cache_key threaded through.
    assert provider.seen_cache_keys[0] == "s1"
    # tools schema is the flat Responses shape (name at top level), with the
    # dot-free Responses-safe name (the live API rejects dotted names).
    assert provider.seen_tools[0][0]["name"] == "files_read"
    assert "function" not in provider.seen_tools[0][0]


@pytest.mark.asyncio
async def test_responses_loop_compacts_stale_tool_outputs(tmp_path: Path) -> None:
    """A long tool-heavy turn must not resend every prior tool result at full size.

    8 files.read calls, each returning a large body. By the time the model is
    asked for its 9th response, the first 2 (8 - KEEP_RECENT_TOOL_RESULTS=6)
    function_call_output items in the outbound message list must be compacted;
    the most recent 6 must remain untouched, full-size.
    """
    big_body = "x" * 5000

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        return ToolExecutionResult(tool_id="files.read", ok=True, summary="Read file", body=big_body)

    turns = [
        [_fc(f"call_{i}", "files.read", {"path": f"file_{i}.txt"}), _COMPLETED] for i in range(8)
    ]
    turns.append([ProviderEvent(kind="delta", text="done"), _COMPLETED])
    provider = ScriptedResponsesProvider(turns=turns)

    await _drain(
        run_with_responses_tools(
            provider=provider,
            messages=[{"role": "user", "content": [{"type": "input_text", "text": "read all the files"}]}],
            abort_event=asyncio.Event(),
            model="gpt-5.5",
            instructions="be helpful",
            plan=_make_plan(),
            tool_executor=tool_executor,
            tool_context=_make_context(tmp_path),
            session_id="s1",
        )
    )

    assert len(provider.seen_messages) == 9
    final_input = provider.seen_messages[-1]
    fco_items = [item for item in final_input if item.get("type") == "function_call_output"]
    assert len(fco_items) == 8
    sizes = [len(item["output"]) for item in fco_items]
    # First 2 (stale) are compacted well below the full 5000-char body.
    assert all(size < 1000 for size in sizes[:2]), sizes
    # Most recent 6 stay full-size, byte-identical to what the tool actually returned.
    assert all(json.loads(item["output"])["body"] == big_body for item in fco_items[2:])
    # Compaction keeps the actionable envelope fields on the stale ones too.
    for item in fco_items[:2]:
        stale = json.loads(item["output"])
        assert stale["ok"] is True
        assert stale["summary"] == "Read file"


@pytest.mark.asyncio
async def test_responses_loop_reverse_maps_sanitized_tool_name(tmp_path: Path) -> None:
    """The model calls the Responses-safe name (files_read); the loop must
    execute the real dotted tool id (files.read)."""
    executed: list[str] = []

    async def tool_executor(request, context):
        executed.append(request.tool_id)
        return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary="ok", body="x")

    provider = ScriptedResponsesProvider(
        turns=[
            [_fc("call_1", "files_read", {"path": "foo.txt"}), _COMPLETED],  # sanitized name, as the real API returns
            [ProviderEvent(kind="delta", text="done"), _COMPLETED],
        ]
    )
    await _drain(
        run_with_responses_tools(
            provider=provider,
            messages=[{"role": "user", "content": [{"type": "input_text", "text": "read it"}]}],
            abort_event=asyncio.Event(),
            model="gpt-5.5",
            instructions=None,
            plan=_make_plan(),
            tool_executor=tool_executor,
            tool_context=_make_context(tmp_path),
            session_id="s1",
        )
    )
    assert executed == ["files.read"]  # reverse-mapped to the real id


@pytest.mark.asyncio
async def test_responses_loop_handles_parallel_tool_calls(tmp_path: Path) -> None:
    calls_executed: list[str] = []

    async def tool_executor(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
        calls_executed.append(request.arguments.get("path"))
        return ToolExecutionResult(tool_id="files.read", ok=True, summary="ok", body=f"body for {request.arguments.get('path')}")

    provider = ScriptedResponsesProvider(
        turns=[
            [
                _fc("call_a", "files.read", {"path": "a.txt"}),
                _fc("call_b", "files.read", {"path": "b.txt"}),
                _COMPLETED,
            ],
            [ProviderEvent(kind="delta", text="done"), _COMPLETED],
        ]
    )

    events = await _drain(
        run_with_responses_tools(
            provider=provider,
            messages=[{"role": "user", "content": [{"type": "input_text", "text": "read both"}]}],
            abort_event=asyncio.Event(),
            model="gpt-5.5",
            instructions=None,
            plan=_make_plan(),
            tool_executor=tool_executor,
            tool_context=_make_context(tmp_path),
            session_id="s1",
        )
    )

    assert calls_executed == ["a.txt", "b.txt"]
    second_input = provider.seen_messages[1]
    fco_items = [i for i in second_input if i.get("type") == "function_call_output"]
    assert {i["call_id"] for i in fco_items} == {"call_a", "call_b"}
    assert events[-1].kind == "final"


@pytest.mark.asyncio
async def test_responses_loop_finalizes_immediately_when_no_tools(tmp_path: Path) -> None:
    async def tool_executor(request, context):  # pragma: no cover - should not run
        raise AssertionError("no tool should be executed")

    provider = ScriptedResponsesProvider(
        turns=[[ProviderEvent(kind="delta", text="just an answer"), _COMPLETED]]
    )

    events = await _drain(
        run_with_responses_tools(
            provider=provider,
            messages=[{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
            abort_event=asyncio.Event(),
            model="gpt-5.5",
            instructions=None,
            plan=_make_plan(),
            tool_executor=tool_executor,
            tool_context=_make_context(tmp_path),
            session_id="s1",
        )
    )
    assert any(e.kind == "delta" and e.text == "just an answer" for e in events)
    assert events[-1].kind == "final"
    assert len(provider.seen_messages) == 1


def test_compose_responses_tool_instructions_tells_model_to_use_tools() -> None:
    from copenet.core.harness.tool_loop import compose_responses_tool_instructions

    text = compose_responses_tool_instructions(
        system_prompt="Be terse.",
        workdir="/work/repo",
        tools=_make_plan().tools,
    )
    assert "Be terse." in text
    assert "/work/repo" in text
    assert "files.read" in text
    # The directive must actively push the model to act, not hedge.
    assert "do NOT claim" in text.lower() or "do not claim" in text.lower()


@pytest.mark.asyncio
async def test_harness_sends_agent_instructions_on_responses_path(tmp_path: Path) -> None:
    """Characterize the complete model input assembled for OpenAI Responses."""
    from copenet.core.harness import ChatHarness

    provider = ScriptedResponsesProvider(turns=[[ProviderEvent(kind="delta", text="hi"), _COMPLETED]])

    async def tool_executor(request, context):  # pragma: no cover
        raise AssertionError("no tool expected")

    input_items = [
        {"role": "user", "content": [{"type": "input_text", "text": "Earlier request"}]},
        {"role": "assistant", "content": [{"type": "output_text", "text": "Earlier answer"}]},
        {"role": "user", "content": [{"type": "input_text", "text": "Read it"}]},
    ]
    _, stream = await ChatHarness().run_turn(
        provider=provider,
        prompt="Read it",
        messages=input_items,
        session_id="s1",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        model="gpt-5.5",
        system_prompt="PROFILE_SENTINEL\n\nACCESS_SENTINEL",
        prompt_context_builder=lambda _plan: PromptOverlay(persona="PERSONA_SENTINEL", memory="MEMORY_SENTINEL"),
        available_tools=_make_plan().tools,
        tool_executor=tool_executor,
        tool_context=_make_context(tmp_path),
    )
    _ = [e async for e in stream]

    assert provider.seen_messages == [input_items]
    assert provider.seen_tools == [
        [
            {
                "type": "function",
                "name": "files_read",
                "description": "Read a file.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                },
            }
        ]
    ]
    instructions = provider.seen_instructions[0]
    assert instructions is not None
    assert instructions.startswith(
        "PROFILE_SENTINEL\n\nACCESS_SENTINEL\n\n"
        "PERSONA_SENTINEL\n\nMEMORY_SENTINEL\n\n"
    )
    assert f"operating in a REAL workspace rooted at {tmp_path}" in instructions
    assert "You have working tools: files.read." in instructions
    assert instructions.index("PROFILE_SENTINEL") < instructions.index("ACCESS_SENTINEL")
    assert instructions.index("ACCESS_SENTINEL") < instructions.index("PERSONA_SENTINEL")
    assert instructions.index("PERSONA_SENTINEL") < instructions.index("MEMORY_SENTINEL")
    assert instructions.index("MEMORY_SENTINEL") < instructions.index("REAL workspace")
    assert provider.seen_cache_keys == ["s1"]


@pytest.mark.asyncio
async def test_harness_enables_reasoning_on_responses_path(tmp_path: Path) -> None:
    """Regression guard: ChatHarness must request reasoning summaries on the
    Responses path, otherwise the Phase 4 inline-thinking UX produces nothing."""
    from copenet.core.harness import ChatHarness, DEFAULT_RESPONSES_REASONING

    (tmp_path / "foo.txt").write_text("hi", encoding="utf-8")
    provider = ScriptedResponsesProvider(turns=[[ProviderEvent(kind="delta", text="hello"), _COMPLETED]])

    async def tool_executor(request, context):  # pragma: no cover - no tools here
        raise AssertionError("no tool expected")

    harness = ChatHarness()
    tools = _make_plan().tools
    plan, stream = await harness.run_turn(
        provider=provider,
        prompt="hi",
        messages=[{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}],
        session_id="sess-1",
        provider_session_id=None,
        abort_event=asyncio.Event(),
        model="gpt-5.5",
        available_tools=tools,
        tool_executor=tool_executor,
        tool_context=_make_context(tmp_path),
    )
    assert plan.tool_execution_mode == "responses"
    _ = [event async for event in stream]
    assert provider.seen_reasoning[0] == DEFAULT_RESPONSES_REASONING
    assert provider.seen_reasoning[0]["summary"] == "auto"
