"""Responses-API native tool loop."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Protocol

from copenet.core.runtime import TurnState
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, build_responses_tool_schemas, responses_safe_tool_name
from copenet.providers import RESOLVED_MODEL_META_KEY, TOKEN_USAGE_META_KEY, ProviderEvent

from . import responses_items
from .context_window import estimate_request_tokens, trim_messages_to_request_budget
from .planning import HarnessTurnPlan
from .tool_loop_common import (
    absorb_loaded_tools,
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
    trace_tool_requested,
)
from .tool_result_materialization import _materialize_tool_result_artifact
from .within_turn_receipts import KEEP_RECENT_STEPS as KEEP_RECENT_STEPS_GUARD, LiveToolResult, apply_within_turn_receipts, remember_result


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
    # What each function_call_output in the array was, so old read-only results can
    # be shrunk to receipts once the request grows past the trigger.
    live_results: dict[str, LiveToolResult] = {}
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
        response_output_items: list[dict[str, Any]] = []
        assistant_text_chunks: list[str] = []
        response_completed = False
        # Re-check the budget on every step because a tool-heavy turn grows the
        # array after each result. Never abbreviate an observation because it got
        # older: file digests, compiler errors, and other control data remain live.
        if len(live_results) > KEEP_RECENT_STEPS_GUARD:
            pass_stats = apply_within_turn_receipts(
                working_messages,
                live_results,
                current_step=step_index + 1,
                request_tokens=estimate_request_tokens(working_messages, instructions=instructions, tools=tool_schemas),
            )
            if pass_stats is not None and trace is not None:
                trace("within_turn_receipts_applied", pass_stats)
        outbound_messages = list(working_messages)
        if input_token_budget:
            bounded = trim_messages_to_request_budget(
                outbound_messages,
                max_input_tokens=input_token_budget,
                instructions=instructions,
                tools=tool_schemas,
            )
            if trace is not None:
                request_estimate = estimate_request_tokens(
                    bounded, instructions=instructions, tools=tool_schemas,
                )
                trace("tool_loop_input_prepared", {
                    "step": step_index + 1,
                    "omittedItemCount": len(outbound_messages) - len(bounded),
                    "inputTokenBudget": input_token_budget,
                    "providerInputTokenEstimate": request_estimate,
                })
                if len(bounded) != len(outbound_messages):
                    trace("tool_loop_input_trimmed", {
                        "step": step_index + 1,
                        "omittedItemCount": len(outbound_messages) - len(bounded),
                        "inputTokenBudget": input_token_budget,
                        "providerInputTokenEstimate": request_estimate,
                    })
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
                if "responsesCompleted" in event.metadata:
                    response_completed = event.metadata["responsesCompleted"] is True
                fc = event.metadata.get("responsesFunctionCall")
                if isinstance(fc, dict) and str(fc.get("name") or "").strip():
                    function_calls.append(fc)
                replay_item = event.metadata.get("responsesOutputItem")
                if isinstance(replay_item, dict):
                    response_output_items.append(dict(replay_item))
                    yield event
                elif event.metadata.get(RESOLVED_MODEL_META_KEY) or event.metadata.get(TOKEN_USAGE_META_KEY):
                    # Forward, don't swallow: this loop owns the stream the
                    # orchestrator sees, so a dropped announcement is a run stamped
                    # with the requested model instead of the answering one, and a
                    # dropped usage block is a turn with no token count.
                    yield event
        if abort_event.is_set():
            turn_state.terminal_reason = "aborted"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(kind="final")
            return
        if not response_completed:
            raise RuntimeError("Responses provider stream ended incomplete")
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
        # Replay provider output items unchanged. They carry opaque reasoning and
        # assistant `phase`, both of which are part of the Responses state contract.
        working_messages.extend(response_output_items)
        if assistant_text and not any(item.get("type") == "message" for item in response_output_items):
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
            trace_tool_requested(
                trace,
                tool_id=name,
                arguments=arguments,
                step=step_index + 1,
                call_id=call_id,
                flags={"responses": True},
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
            output_text = _native_tool_message_content(tool_result)
            working_messages.append(
                responses_items.function_call_output_item(call_id=call_id, output=output_text)
            )
            remember_result(
                live_results,
                call_id=call_id,
                step=step_index + 1,
                tool_id=tool_result.tool_id,
                ok=tool_result.ok,
                summary=tool_result.summary,
                error=tool_result.error,
                artifact_id=tool_result.artifact_id,
                arguments=arguments,
                output=output_text if isinstance(output_text, str) else str(output_text),
            )
            turn_state.drain_pending_input()
            if trace is not None:
                trace("turn_transition", turn_state.to_public_dict())

        newly_loaded = absorb_loaded_tools(plan, tool_context)
        if newly_loaded:
            tool_schemas = build_responses_tool_schemas(plan.tools)
            safe_name_to_tool_id = {responses_safe_tool_name(tool.id): tool.id for tool in plan.tools}
        if cap_reached:
            turn_state.terminal_reason = "max_turns"
            if trace is not None:
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(kind="delta", text=_max_step_explanation())
            yield ProviderEvent(kind="final")
            return

    yield ProviderEvent(kind="final")
