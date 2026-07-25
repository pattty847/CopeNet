"""OpenAI-compatible native chat-completions tool loop."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol

from copenet.core.runtime import TurnState
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, build_openai_tool_schemas
from copenet.providers import ProviderEvent

from .planning import HarnessTurnPlan
from .tool_loop_common import (
    MAX_TOOL_STEPS,
    ToolExecutor,
    TraceRecorder,
    _coerce_native_message_content,
    _extract_native_choice,
    _extract_native_tool_calls,
    _force_call_id,
    _max_step_explanation,
    _native_tool_message_content,
    _new_call_id,
    _parse_native_tool_arguments,
    _tool_call_event_payload,
    _tool_result_event_payload,
    compact_stale_chat_messages,
    compose_native_tool_system_prompt,
)
from .tool_result_materialization import _materialize_tool_result_artifact


class NativeToolProvider(Protocol):
    name: str

    async def chat_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        model: str | None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Run one non-streaming native tool-capable chat completion."""


async def run_with_native_tools(
    *,
    provider: NativeToolProvider,
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
    """Run an OpenAI-compatible native tool loop without parsing final text."""
    del abort_event
    turn_state = TurnState(turn_id=plan.turn_id, decision_id=plan.decision_id)
    tool_schemas = build_openai_tool_schemas(plan.tools)
    current_system_prompt = compose_native_tool_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
    )
    messages: list[dict[str, Any]] = []
    if current_system_prompt:
        messages.append({"role": "system", "content": current_system_prompt})
    messages.append({"role": "user", "content": prompt})
    latest_content = ""
    if trace is not None:
        trace("turn_started", turn_state.to_public_dict())

    for step_index in range(MAX_TOOL_STEPS):
        response = await provider.chat_completion(
            messages=compact_stale_chat_messages(messages),
            model=model,
            tools=tool_schemas or None,
        )
        message, finish_reason = _extract_native_choice(response)
        content = _coerce_native_message_content(message.get("content"))
        if content:
            latest_content = content
        native_tool_calls = _extract_native_tool_calls(message.get("tool_calls"))
        if trace is not None:
            trace(
                "provider_response_interpreted",
                {
                    "phase": "native",
                    "responseKind": "native_tool_call" if native_tool_calls else "native_final",
                    "toolCallCount": len(native_tool_calls),
                    "contentLength": len(content),
                    "finishReason": finish_reason,
                },
            )

        if not native_tool_calls:
            turn_state.terminal_reason = "completed"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            if content:
                yield ProviderEvent(kind="delta", text=content, provider_session_id=provider_session_id)
            yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
            return

        assistant_message: dict[str, Any] = {"role": "assistant", "tool_calls": native_tool_calls}
        if content:
            assistant_message["content"] = content
        messages.append(assistant_message)
        for native_call in native_tool_calls:
            tool_id = native_call["function"]["name"]
            arguments = _parse_native_tool_arguments(native_call["function"].get("arguments"))
            request = ToolExecutionRequest(tool_id=tool_id, arguments=arguments)
            call_id = str(native_call.get("id") or "").strip() or _new_call_id(request.tool_id)
            if trace is not None:
                trace(
                    "tool_requested",
                    {
                        "toolId": request.tool_id,
                        "arguments": request.arguments,
                        "step": step_index + 1,
                        "native": True,
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
                        native=True,
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
            if trace is not None:
                trace(
                    "tool_result_normalized",
                    {
                        "toolId": tool_result.tool_id,
                        "callId": tool_result.call_id,
                        "channel": tool_result.channel,
                        "success": tool_result.ok,
                        "artifactId": tool_result.artifact_id,
                        "native": True,
                    },
                )
                trace("turn_transition", turn_state.to_public_dict())
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": _native_tool_message_content(tool_result),
                }
            )
            turn_state.drain_pending_input()
        if trace is not None:
            trace(
                "tool_loop_continued",
                {
                    "step": step_index + 1,
                    "native": True,
                    "lastToolId": native_tool_calls[-1]["function"]["name"],
                },
            )
        if step_index >= MAX_TOOL_STEPS - 1:
            turn_state.terminal_reason = "max_turns"
            if trace is not None:
                trace(
                    "tool_loop_max_steps",
                    {
                        "path": "native_tool_call",
                        "step": step_index + 1,
                        "contentLength": len(latest_content),
                    },
                )
                trace("turn_completed", turn_state.to_public_dict())
            cap_hint = _max_step_explanation()
            yield ProviderEvent(
                kind="delta",
                text=(latest_content + "\n\n" + cap_hint) if latest_content else cap_hint,
                provider_session_id=provider_session_id,
            )
            yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
            return

    yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
