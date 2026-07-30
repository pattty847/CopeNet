from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator

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


class _PromptedCapProvider:
    name = "prompted-cap"

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ) -> AsyncIterator[ProviderEvent]:
        del prompt, abort_event, model, system_prompt
        blocks = [
            (
                f"{PROMPTED_TOOL_OPEN}"
                + json.dumps({"tool_id": "files.read", "arguments": {"path": f"{index}.txt"}})
                + f"{PROMPTED_TOOL_CLOSE}"
            )
            for index in range(MAX_TOOL_STEPS + 1)
        ]
        yield ProviderEvent(
            kind="delta",
            text="\n".join(blocks),
            provider_session_id=provider_session_id or "prompted-session",
        )
        yield ProviderEvent(kind="final")


class _NativeCapProvider:
    name = "native-cap"

    async def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del messages, model, tools, tool_choice
        return {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "role": "assistant",
                        "tool_calls": [
                            {
                                "id": f"call-{index}",
                                "type": "function",
                                "function": {
                                    "name": "files.read",
                                    "arguments": json.dumps({"path": f"{index}.txt"}),
                                },
                            }
                            for index in range(MAX_TOOL_STEPS + 1)
                        ],
                    },
                }
            ]
        }


class _ResponsesCapProvider:
    name = "responses-cap"

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
        del (
            messages,
            tools,
            model,
            instructions,
            prompt_cache_key,
            reasoning,
            parallel_tool_calls,
            abort_event,
        )
        for index in range(MAX_TOOL_STEPS + 1):
            yield ProviderEvent(
                kind="meta",
                metadata={
                    "responsesFunctionCall": {
                        "id": f"fc-{index}",
                        "call_id": f"call-{index}",
                        "name": "files_read",
                        "arguments": json.dumps({"path": f"{index}.txt"}),
                    }
                },
            )


def _plan(loop_kind: str) -> HarnessTurnPlan:
    return HarnessTurnPlan(
        provider=f"{loop_kind}-cap",
        model="test-model",
        capability_profile=ModelCapabilityProfile(
            provider=f"{loop_kind}-cap",
            model="test-model",
            tool_calls=loop_kind == "native",
            prompted_tool_use=loop_kind == "prompted",
            responses_api=loop_kind == "responses",
        ),
        tools=[_TOOL],
        will_attempt_tool_loop=True,
        tool_execution_mode=loop_kind,  # type: ignore[arg-type]
    )


def _context(tmp_path: Path, loop_kind: str) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="cap-contract",
        provider_name=f"{loop_kind}-cap",
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
        run_id="cap-contract-run",
        trace=None,
    )


@pytest.mark.parametrize("loop_kind", ["prompted", "native", "responses"])
@pytest.mark.asyncio
async def test_tool_loops_execute_only_max_tool_steps_and_explain_the_cap(
    loop_kind: str,
    tmp_path: Path,
) -> None:
    attempted_count = MAX_TOOL_STEPS + 1
    executions: list[ToolExecutionRequest] = []
    traces: list[tuple[str, dict[str, Any]]] = []

    async def execute(
        request: ToolExecutionRequest,
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        del context
        executions.append(request)
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="scripted read",
            body={"path": request.arguments["path"]},
        )

    def trace(event: str, payload: dict[str, Any] | None) -> None:
        traces.append((event, payload or {}))

    common = {
        "abort_event": asyncio.Event(),
        "model": "test-model",
        "plan": _plan(loop_kind),
        "tool_executor": execute,
        "tool_context": _context(tmp_path, loop_kind),
        "trace": trace,
    }
    if loop_kind == "prompted":
        stream = run_with_prompted_tools(
            provider=_PromptedCapProvider(),
            prompt="read the scripted files",
            provider_session_id=None,
            system_prompt=None,
            **common,
        )
        interpreted_event = "prompted_tool_response_interpreted"
        attempted_key = "toolCallCount"
    elif loop_kind == "native":
        stream = run_with_native_tools(
            provider=_NativeCapProvider(),
            prompt="read the scripted files",
            provider_session_id=None,
            system_prompt=None,
            **common,
        )
        interpreted_event = "provider_response_interpreted"
        attempted_key = "toolCallCount"
    else:
        stream = run_with_responses_tools(
            provider=_ResponsesCapProvider(),
            messages=[{"role": "user", "content": "read the scripted files"}],
            instructions=None,
            session_id="cap-contract",
            **common,
        )
        interpreted_event = "responses_turn_interpreted"
        attempted_key = "functionCallCount"

    events = [event async for event in stream]
    interpreted = next(payload for event, payload in traces if event == interpreted_event)
    completed = next(payload for event, payload in traces if event == "turn_completed")
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
