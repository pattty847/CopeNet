"""Responses-API native tool loop."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol

from copenet.core.runtime import TurnState
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, build_responses_tool_schemas, responses_safe_tool_name
from copenet.providers import ProviderEvent

from . import responses_items
from .context_window import estimate_input_tokens, trim_messages_to_token_budget
from .planning import HarnessTurnPlan
from .tool_loop_common import (
    MAX_TOOL_STEPS,
    ToolExecutor,
    TraceRecorder,
    _bounded_tool_calls,
    _force_call_id,
    _max_step_explanation,
    _native_tool_message_content,
    _new_call_id,
    _parse_native_tool_arguments,
    _tool_call_event_payload,
    _tool_result_event_payload,
    compact_stale_responses_items,
)
from .tool_result_materialization import _materialize_tool_result_artifact


class ResponsesProvider(Protocol):
    name: str

    def stream_responses(
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
        """Stream one Responses-API turn over a pre-built input[] array."""


async def run_with_responses_tools(
    *,
    provider: ResponsesProvider,
    messages: list[dict[str, Any]],
    abort_event: asyncio.Event,
    model: str | None,
    instructions: str | None,
    plan: HarnessTurnPlan,
    tool_executor: ToolExecutor,
    tool_context: ToolExecutionContext,
    session_id: str | None,
    reasoning: dict[str, Any] | None = None,
    input_token_budget: int | None = None,
    trace: TraceRecorder | None = None,
) -> AsyncIterator[ProviderEvent]:
    """Native Responses-API tool loop (Phase 2, HARNESS_REBUILD_V2).

    Owns the input[] array. Streams a response; collects function_call items via
    the provider's responsesFunctionCall meta events; executes each tool; appends
    function_call + function_call_output items to the array; re-POSTs. Emits the
    same toolCall / toolExecution meta + delta events as the other loops so the
    runtime's transcript-part assembly is unchanged. Reasoning summary deltas pass
    through as reasoning_delta events for the Phase 4 inline-thinking UX.
    """
    turn_state = TurnState(turn_id=plan.turn_id, decision_id=plan.decision_id)
    tool_schemas = build_responses_tool_schemas(plan.tools)
    # The provider sees Responses-safe (dot-free) function names; map them back to
    # the real dotted tool ids when the model calls them.
    safe_name_to_tool_id = {responses_safe_tool_name(tool.id): tool.id for tool in plan.tools}
    working_messages: list[dict[str, Any]] = [dict(item) for item in messages]
    if trace is not None:
        trace("turn_started", turn_state.to_public_dict())

    for step_index in range(MAX_TOOL_STEPS):
        if abort_event.is_set():
            turn_state.terminal_reason = "aborted"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(kind="final")
            return
        function_calls: list[dict[str, Any]] = []
        assistant_text_chunks: list[str] = []
        # Compact stale tool output first (cheap, lossy only for old observations),
        # then enforce the budget on what remains. Trimming once before the loop is
        # not enough: a long agentic turn grows the array on every step.
        outbound_messages = compact_stale_responses_items(working_messages)
        if input_token_budget:
            bounded = trim_messages_to_token_budget(
                outbound_messages, max_context_tokens=input_token_budget
            )
            if trace is not None and len(bounded) != len(outbound_messages):
                trace(
                    "tool_loop_input_trimmed",
                    {
                        "step": step_index + 1,
                        "omittedItemCount": len(outbound_messages) - len(bounded),
                        "inputTokenBudget": input_token_budget,
                        "inputTokenEstimate": estimate_input_tokens(bounded),
                    },
                )
            outbound_messages = bounded
        async for event in provider.stream_responses(
            messages=outbound_messages,
            tools=tool_schemas or None,
            model=model,
            instructions=instructions,
            prompt_cache_key=session_id,
            reasoning=reasoning,
            parallel_tool_calls=True,
            abort_event=abort_event,
        ):
            if event.kind == "delta":
                if event.text:
                    assistant_text_chunks.append(event.text)
                yield event
            elif event.kind == "reasoning_delta":
                yield event
            elif event.kind == "meta" and isinstance(event.metadata, dict):
                fc = event.metadata.get("responsesFunctionCall")
                if isinstance(fc, dict) and str(fc.get("name") or "").strip():
                    function_calls.append(fc)
        assistant_text = "".join(assistant_text_chunks).strip()
        if trace is not None:
            trace(
                "responses_turn_interpreted",
                {
                    "step": step_index + 1,
                    "functionCallCount": len(function_calls),
                    "contentLength": len(assistant_text),
                },
            )

        if not function_calls:
            turn_state.terminal_reason = "completed"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(kind="final")
            return

        function_calls, cap_reached = _bounded_tool_calls(
            function_calls,
            completed_count=turn_state.tool_call_count,
        )
        # Append assistant text item (if any) so the model sees its own narration
        # on the next replay, then each function_call item.
        if assistant_text:
            working_messages.append(
                responses_items.assistant_message_item(
                    message_id=f"msg_{plan.turn_id}_{step_index}", text=assistant_text
                )
            )
        for call in function_calls:
            if abort_event.is_set():
                # Stop before running any more tools — they have real side effects
                # (shell.exec, files.write). Already-appended function_call items
                # without an output are fine; the loop terminates below.
                turn_state.terminal_reason = "aborted"
                if trace is not None:
                    trace("turn_completed", turn_state.to_public_dict())
                yield ProviderEvent(kind="final")
                return
            call_id = str(call.get("call_id") or "").strip() or _new_call_id(str(call.get("name") or "tool"))
            raw_name = str(call.get("name") or "").strip()
            # Reverse the name sanitization: the model emits the safe name; we
            # execute and record the real dotted tool id.
            name = safe_name_to_tool_id.get(raw_name, raw_name)
            arguments_json = str(call.get("arguments") or "").strip() or "{}"
            arguments = _parse_native_tool_arguments(arguments_json)
            working_messages.append(
                responses_items.function_call_item(
                    item_id=str(call.get("id") or "") or f"fc_{call_id}",
                    call_id=call_id,
                    name=name,
                    arguments=arguments_json,
                )
            )
            request = ToolExecutionRequest(tool_id=name, arguments=arguments)
            if trace is not None:
                trace(
                    "tool_requested",
                    {
                        "toolId": name,
                        "arguments": arguments,
                        "step": step_index + 1,
                        "responses": True,
                        "callId": call_id,
                    },
                )
            yield ProviderEvent(
                kind="meta",
                metadata={
                    "toolCall": _tool_call_event_payload(
                        tool_id=name,
                        arguments=arguments,
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
                arguments=arguments,
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
            working_messages.append(
                responses_items.function_call_output_item(
                    call_id=call_id,
                    output=_native_tool_message_content(tool_result),
                )
            )
            turn_state.drain_pending_input()
            if trace is not None:
                trace("turn_transition", turn_state.to_public_dict())

        if cap_reached:
            turn_state.terminal_reason = "max_turns"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(kind="delta", text=_max_step_explanation())
            yield ProviderEvent(kind="final")
            return

    yield ProviderEvent(kind="final")
