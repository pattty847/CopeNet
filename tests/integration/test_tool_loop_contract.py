from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any, AsyncIterator, Literal

import pytest

from copenet.core.harness.capabilities import ModelCapabilityProfile
from copenet.core.harness.planning import HarnessTurnPlan
from copenet.core.harness.tool_loop import (
    MAX_TOOL_STEPS,
    run_with_native_tools,
    run_with_prompted_tools,
    run_with_responses_tools,
)
from copenet.core.harness.tool_loop_common import PROMPTED_TOOL_CLOSE, PROMPTED_TOOL_OPEN
from copenet.core.tools import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolPolicy,
)
from copenet.providers import ProviderEvent


LoopKind = Literal["prompted", "native", "responses"]
_LOOP_KINDS: tuple[LoopKind, ...] = ("prompted", "native", "responses")
_TOOL = ToolDescriptor(
    id="files.read",
    name="Read File",
    description="Read a file.",
    category="repo-read",
    input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
    capabilities=["filesystem", "read"],
    evidence_role="grounding",
    side_effect="read",
)


@dataclass(frozen=True)
class _ScriptedTurn:
    calls: list[dict[str, Any]] = field(default_factory=list)
    text: str = ""


class _PromptedProvider:
    name = "prompted-contract"

    def __init__(self, turns: list[_ScriptedTurn]) -> None:
        self._turns = turns
        self.seen_prompts: list[str] = []

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        del abort_event, model, system_prompt
        self.seen_prompts.append(prompt)
        turn = self._turns[len(self.seen_prompts) - 1]
        blocks = [
            f"{PROMPTED_TOOL_OPEN}{json.dumps(call)}{PROMPTED_TOOL_CLOSE}"
            for call in turn.calls
        ]
        text = "\n".join([*blocks, turn.text]).strip()
        if text:
            yield ProviderEvent(
                kind="delta",
                text=text,
                provider_session_id=provider_session_id or "prompted-session",
            )
        yield ProviderEvent(kind="final")


class _NativeProvider:
    name = "native-contract"

    def __init__(self, turns: list[_ScriptedTurn]) -> None:
        self._turns = turns
        self.seen_messages: list[list[dict[str, Any]]] = []

    async def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del model, tools, tool_choice
        self.seen_messages.append([dict(message) for message in messages])
        turn = self._turns[len(self.seen_messages) - 1]
        tool_calls = [
            {
                "id": f"call-{index}",
                "type": "function",
                "function": {
                    "name": call["tool_id"],
                    "arguments": json.dumps(call["arguments"]),
                },
            }
            for index, call in enumerate(turn.calls)
        ]
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls" if tool_calls else "stop",
                    "message": {
                        "role": "assistant",
                        "content": turn.text,
                        "tool_calls": tool_calls,
                    },
                }
            ]
        }


class _ResponsesProvider:
    name = "responses-contract"

    def __init__(self, turns: list[_ScriptedTurn]) -> None:
        self._turns = turns
        self.seen_messages: list[list[dict[str, Any]]] = []

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
        del tools, model, instructions, prompt_cache_key, reasoning, parallel_tool_calls, abort_event
        self.seen_messages.append([dict(message) for message in messages])
        turn = self._turns[len(self.seen_messages) - 1]
        for index, call in enumerate(turn.calls):
            yield ProviderEvent(
                kind="meta",
                metadata={
                    "responsesFunctionCall": {
                        "id": f"fc-{index}",
                        "call_id": f"call-{index}",
                        "name": call["tool_id"].replace(".", "_"),
                        "arguments": json.dumps(call["arguments"]),
                    }
                },
            )
        if turn.text:
            yield ProviderEvent(kind="delta", text=turn.text)


def _call(index: int = 0) -> dict[str, Any]:
    return {
        "tool_id": "files.read",
        "arguments": {"path": f"file-{index}.txt"},
    }


def _provider(loop_kind: LoopKind, turns: list[_ScriptedTurn]) -> Any:
    if loop_kind == "prompted":
        return _PromptedProvider(turns)
    if loop_kind == "native":
        return _NativeProvider(turns)
    return _ResponsesProvider(turns)


def _plan(loop_kind: LoopKind) -> HarnessTurnPlan:
    return HarnessTurnPlan(
        provider=f"{loop_kind}-contract",
        model="test-model",
        capability_profile=ModelCapabilityProfile(
            provider=f"{loop_kind}-contract",
            model="test-model",
            tool_calls=loop_kind == "native",
            prompted_tool_use=loop_kind == "prompted",
            responses_api=loop_kind == "responses",
        ),
        tools=[_TOOL],
        will_attempt_tool_loop=True,
        tool_execution_mode=loop_kind,
    )


def _context(tmp_path: Path, loop_kind: LoopKind) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="tool-loop-contract",
        provider_name=f"{loop_kind}-contract",
        model="test-model",
        session_store=None,  # type: ignore[arg-type]
        transcript_store=None,  # type: ignore[arg-type]
        providers={},
        policy=ToolPolicy(),
        available_tools=[_TOOL],
        memory_service=None,
        workspace_intel_service=None,
        artifact_store=None,
        task_prompt_id=None,
        run_id="tool-loop-contract-run",
        trace=None,
    )


async def _run_contract(
    *,
    loop_kind: LoopKind,
    turns: list[_ScriptedTurn],
    executor,
    tmp_path: Path,
    abort_event: asyncio.Event | None = None,
) -> tuple[Any, list[ProviderEvent], list[tuple[str, dict[str, Any]]]]:
    provider = _provider(loop_kind, turns)
    traces: list[tuple[str, dict[str, Any]]] = []

    def trace(event: str, payload: dict[str, Any] | None) -> None:
        traces.append((event, payload or {}))

    common = {
        "abort_event": abort_event or asyncio.Event(),
        "model": "test-model",
        "plan": _plan(loop_kind),
        "tool_executor": executor,
        "tool_context": _context(tmp_path, loop_kind),
        "trace": trace,
    }
    if loop_kind == "prompted":
        stream = run_with_prompted_tools(
            provider=provider,
            prompt="run the scripted contract",
            provider_session_id=None,
            system_prompt=None,
            **common,
        )
    elif loop_kind == "native":
        stream = run_with_native_tools(
            provider=provider,
            prompt="run the scripted contract",
            provider_session_id=None,
            system_prompt=None,
            **common,
        )
    else:
        stream = run_with_responses_tools(
            provider=provider,
            messages=[{"role": "user", "content": "run the scripted contract"}],
            instructions=None,
            session_id="tool-loop-contract",
            **common,
        )
    return provider, [event async for event in stream], traces


def _completed_trace(traces: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    return next(payload for event, payload in traces if event == "turn_completed")


@pytest.mark.parametrize("loop_kind", _LOOP_KINDS)
@pytest.mark.asyncio
async def test_tool_loops_execute_and_correlate_one_tool_call(
    loop_kind: LoopKind,
    tmp_path: Path,
) -> None:
    executions: list[ToolExecutionRequest] = []

    async def execute(request, _context):
        executions.append(request)
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="read complete",
            body={"content": "contract result"},
        )

    _, events, traces = await _run_contract(
        loop_kind=loop_kind,
        turns=[_ScriptedTurn(calls=[_call()]), _ScriptedTurn(text="contract complete")],
        executor=execute,
        tmp_path=tmp_path,
    )

    call_event = next(event for event in events if event.metadata and event.metadata.get("toolCall"))
    result_event = next(
        event for event in events if event.metadata and event.metadata.get("toolExecution")
    )
    tool_call = call_event.metadata["toolCall"]
    tool_result = result_event.metadata["toolExecution"]

    assert executions == [ToolExecutionRequest(tool_id="files.read", arguments={"path": "file-0.txt"})]
    assert tool_call["callId"] == tool_result["callId"]
    assert tool_call["turnId"] == tool_result["turnId"]
    assert tool_call["decisionId"] == tool_result["decisionId"]
    assert tool_result["ok"] is True
    assert tool_result["summary"] == "read complete"
    assert any(event.kind == "delta" and event.text == "contract complete" for event in events)
    assert _completed_trace(traces)["terminalReason"] == "completed"
    assert [event.kind for event in events].count("final") == 1
    assert events[-1].kind == "final"


@pytest.mark.parametrize("loop_kind", _LOOP_KINDS)
@pytest.mark.asyncio
async def test_tool_loops_replay_actionable_failure_envelope(
    loop_kind: LoopKind,
    tmp_path: Path,
) -> None:
    async def execute(request, _context):
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=False,
            summary="read denied by policy",
            error="permission denied",
        )

    provider, _, _ = await _run_contract(
        loop_kind=loop_kind,
        turns=[_ScriptedTurn(calls=[_call()]), _ScriptedTurn(text="denial handled")],
        executor=execute,
        tmp_path=tmp_path,
    )

    if loop_kind == "prompted":
        replay = provider.seen_prompts[1]
        assert '"ok": false' in replay
        assert '"summary": "read denied by policy"' in replay
        assert '"error": "permission denied"' in replay
    elif loop_kind == "native":
        tool_message = next(message for message in provider.seen_messages[1] if message["role"] == "tool")
        replay = json.loads(tool_message["content"])
        assert replay["ok"] is False
        assert replay["summary"] == "read denied by policy"
        assert replay["error"] == "permission denied"
    else:
        output = next(
            item["output"]
            for item in provider.seen_messages[1]
            if item.get("type") == "function_call_output"
        )
        replay = json.loads(output)
        assert replay["ok"] is False
        assert replay["summary"] == "read denied by policy"
        assert replay["error"] == "permission denied"


@pytest.mark.parametrize("loop_kind", _LOOP_KINDS)
@pytest.mark.asyncio
async def test_tool_loops_stop_before_the_next_side_effect_after_abort(
    loop_kind: LoopKind,
    tmp_path: Path,
) -> None:
    abort_event = asyncio.Event()
    executions: list[ToolExecutionRequest] = []

    async def execute(request, _context):
        executions.append(request)
        abort_event.set()
        return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary="first call complete")

    _, events, traces = await _run_contract(
        loop_kind=loop_kind,
        turns=[_ScriptedTurn(calls=[_call(0), _call(1)])],
        executor=execute,
        tmp_path=tmp_path,
        abort_event=abort_event,
    )

    assert executions == [ToolExecutionRequest(tool_id="files.read", arguments={"path": "file-0.txt"})]
    assert len([event for event in events if event.metadata and event.metadata.get("toolExecution")]) == 1
    assert _completed_trace(traces)["terminalReason"] == "aborted"
    assert [event.kind for event in events].count("final") == 1
    assert events[-1].kind == "final"


@pytest.mark.parametrize("loop_kind", _LOOP_KINDS)
@pytest.mark.asyncio
async def test_tool_loops_enforce_the_global_tool_call_budget(
    loop_kind: LoopKind,
    tmp_path: Path,
) -> None:
    attempted_count = MAX_TOOL_STEPS + 1
    executions: list[ToolExecutionRequest] = []

    async def execute(request, _context):
        executions.append(request)
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="scripted read",
            body={"path": request.arguments["path"]},
        )

    _, events, traces = await _run_contract(
        loop_kind=loop_kind,
        turns=[_ScriptedTurn(calls=[_call(index) for index in range(attempted_count)])],
        executor=execute,
        tmp_path=tmp_path,
    )
    interpreted_event = {
        "prompted": "prompted_tool_response_interpreted",
        "native": "provider_response_interpreted",
        "responses": "responses_turn_interpreted",
    }[loop_kind]
    attempted_key = "functionCallCount" if loop_kind == "responses" else "toolCallCount"
    interpreted = next(payload for event, payload in traces if event == interpreted_event)
    completed = _completed_trace(traces)
    cap_explanation = (
        f"[Stopped after MAX_TOOL_STEPS={MAX_TOOL_STEPS} tool calls. "
        "Returning what was produced so far.]"
    )

    assert interpreted[attempted_key] == attempted_count
    assert len(executions) == MAX_TOOL_STEPS
    assert len([event for event in events if event.metadata and event.metadata.get("toolExecution")]) == MAX_TOOL_STEPS
    assert completed["toolCallCount"] == MAX_TOOL_STEPS
    assert completed["terminalReason"] == "max_turns"
    assert any(event.kind == "delta" and cap_explanation in (event.text or "") for event in events)
    assert [event.kind for event in events].count("final") == 1
    assert events[-1].kind == "final"
