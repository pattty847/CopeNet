"""Prompted text-protocol tool loop."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from copenet.core.runtime import TurnState
from copenet.core.tools import ToolExecutionContext
from copenet.providers import Provider, ProviderEvent

from .planning import HarnessTurnPlan
from .tool_loop_common import (
    MAX_TOOL_STEPS,
    ToolExecutor,
    TraceRecorder,
    _compose_prompted_tool_followup,
    _extract_prompted_tool_requests,
    _force_call_id,
    _max_step_explanation,
    _new_call_id,
    _tool_call_event_payload,
    _tool_result_event_payload,
    collect_provider_turn,
    compose_prompted_tool_system_prompt,
)
from .tool_result_materialization import _materialize_tool_result_artifact


async def run_with_prompted_tools(
    *,
    provider: Provider,
    prompt: str,
    provider_session_id: str | None,
    abort_event: asyncio.Event,
    model: str | None,
    system_prompt: str | None,
    plan: HarnessTurnPlan,
    tool_executor: ToolExecutor,
    tool_context: ToolExecutionContext,
    trace: TraceRecorder | None,
) -> AsyncIterator[ProviderEvent]:
    """Run a bounded text-protocol tool loop for providers without native tools."""
    discovered_session = provider_session_id
    current_prompt = prompt
    current_system_prompt = compose_prompted_tool_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        tools=plan.tools,
    )
    turn_state = TurnState(turn_id=plan.turn_id, decision_id=plan.decision_id)
    if trace is not None:
        trace("turn_started", turn_state.to_public_dict())

    for step_index in range(MAX_TOOL_STEPS):
        events, discovered_session = await collect_provider_turn(
            provider=provider,
            prompt=current_prompt,
            provider_session_id=discovered_session,
            abort_event=abort_event,
            model=model,
            system_prompt=current_system_prompt,
            trace=trace,
            phase="prompted_tool",
        )
        assistant_text = "".join(event.text or "" for event in events if event.kind == "delta").strip()
        tool_requests = _extract_prompted_tool_requests(assistant_text)
        if trace is not None:
            trace(
                "prompted_tool_response_interpreted",
                {
                    "toolCallCount": len(tool_requests),
                    "contentLength": len(assistant_text),
                    "step": step_index + 1,
                },
            )
        if not tool_requests:
            turn_state.terminal_reason = "completed"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            if assistant_text:
                yield ProviderEvent(kind="delta", text=assistant_text, provider_session_id=discovered_session)
            yield ProviderEvent(kind="final", provider_session_id=discovered_session)
            return

        tool_payloads: list[str] = []
        for request in tool_requests:
            call_id = _new_call_id(request.tool_id)
            if trace is not None:
                trace(
                    "tool_requested",
                    {
                        "toolId": request.tool_id,
                        "arguments": request.arguments,
                        "step": step_index + 1,
                        "native": False,
                        "callId": call_id,
                    },
                )
            yield ProviderEvent(
                kind="meta",
                metadata={
                    "toolCall": _tool_call_event_payload(
                        tool_id=request.tool_id,
                        arguments=request.arguments,
                        step=step_index + 1,
                        turn_id=plan.turn_id,
                        decision_id=plan.decision_id,
                        native=False,
                        call_id=call_id,
                    ),
                    "turnState": turn_state.to_public_dict(),
                },
            )
            tool_result = await tool_executor(request, tool_context)
            tool_result = _force_call_id(tool_result, call_id)
            tool_result, artifact_draft = _materialize_tool_result_artifact(
                tool_result=tool_result,
                tool_context=tool_context,
                trace=trace,
            )
            turn_state.tool_call_count += 1
            turn_state.record_tool_step(
                tool_id=tool_result.tool_id,
                arguments=request.arguments,
                result=tool_result,
            )
            turn_state.queue_input(tool_result.to_runtime_input(), reason="tool_followup")
            meta_payload: dict[str, Any] = {
                "toolExecution": _tool_result_event_payload(
                    result=tool_result,
                    request=request,
                    plan=plan,
                ),
                "toolResult": tool_result.to_runtime_input(),
                "turnState": turn_state.to_public_dict(),
            }
            if artifact_draft is not None:
                meta_payload["artifactDraft"] = artifact_draft
            yield ProviderEvent(kind="meta", metadata=meta_payload)
            tool_payloads.append(tool_result.to_prompt_payload())
            turn_state.drain_pending_input()
            if trace is not None:
                trace("turn_transition", turn_state.to_public_dict())
        if step_index >= MAX_TOOL_STEPS - 1:
            turn_state.terminal_reason = "max_turns"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(
                kind="delta",
                text=_max_step_explanation(),
                provider_session_id=discovered_session,
            )
            yield ProviderEvent(kind="final", provider_session_id=discovered_session)
            return
        current_prompt = _compose_prompted_tool_followup(
            user_prompt=prompt,
            assistant_text=assistant_text,
            tool_payloads=tool_payloads,
        )

    turn_state.terminal_reason = "max_turns"
    if trace is not None:
        trace("turn_completed", turn_state.to_public_dict())
    yield ProviderEvent(kind="final", provider_session_id=discovered_session)
