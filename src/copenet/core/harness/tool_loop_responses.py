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
    extract_activity_title,
    _max_step_explanation,
    _native_tool_message_content,
    _new_call_id,
    _parse_native_tool_arguments,
    _tool_call_event_payload,
    _tool_result_event_payload,
    trace_tool_requested,
)
from .tool_result_materialization import _materialize_tool_result_artifact

# A provider stream that dies mid-body (IncompleteRead, connection reset) is
# re-requested this many times in total, with a short growing pause between.
RESPONSES_STREAM_ATTEMPTS = 2
RESPONSES_STREAM_RETRY_DELAY_SEC = 1.5


def _retryable_stream_error(exc: BaseException) -> bool:
    return "stream ended incomplete" in str(exc)


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
        response_output_items: list[dict[str, Any]] = []
        assistant_text_chunks: list[str] = []
        response_completed = False
        # Re-check the budget on every step because a tool-heavy turn grows the
        # array after each result. Never abbreviate an observation because it got
        # older: file digests, compiler errors, and other control data remain live.
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
        # A dropped stream is retried only while nothing from the attempt has
        # reached the operator or the transcript: no text, no reasoning, no output
        # item. Up to that point a step is idempotent — the array is untouched and
        # no tool has run — so re-asking is safe. Past it, a retry would duplicate
        # what was already shown or stored, and the error stands.
        for attempt in range(1, RESPONSES_STREAM_ATTEMPTS + 1):
            function_calls = []
            response_output_items = []
            assistant_text_chunks = []
            response_completed = False
            yielded_from_attempt = False
            try:
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
                        yielded_from_attempt = True
                        yield event
                    elif event.kind == "reasoning_delta":
                        yielded_from_attempt = True
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
                            yielded_from_attempt = True
                            yield event
                        elif event.metadata.get(RESOLVED_MODEL_META_KEY) or event.metadata.get(TOKEN_USAGE_META_KEY):
                            # Forward, don't swallow: this loop owns the stream the
                            # orchestrator sees, so a dropped announcement is a run stamped
                            # with the requested model instead of the answering one, and a
                            # dropped usage block is a turn with no token count.
                            yield event
            except RuntimeError as exc:
                if not _retryable_stream_error(exc) or yielded_from_attempt or abort_event.is_set() or attempt >= RESPONSES_STREAM_ATTEMPTS:
                    raise
                if trace is not None:
                    trace("provider_stream_retry", {"step": step_index + 1, "attempt": attempt, "error": str(exc)[:200]})
                await asyncio.sleep(RESPONSES_STREAM_RETRY_DELAY_SEC * attempt)
                continue
            if abort_event.is_set():
                turn_state.terminal_reason = "aborted"
                if trace is not None:
                    trace("turn_completed", turn_state.to_public_dict())
                yield ProviderEvent(kind="final")
                return
            if response_completed:
                break
            if yielded_from_attempt or attempt >= RESPONSES_STREAM_ATTEMPTS:
                raise RuntimeError("Responses provider stream ended incomplete")
            if trace is not None:
                trace("provider_stream_retry", {"step": step_index + 1, "attempt": attempt, "error": "stream ended without response.completed"})
            await asyncio.sleep(RESPONSES_STREAM_RETRY_DELAY_SEC * attempt)
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
            activity_title = extract_activity_title(arguments)
            working_messages.append(
                responses_items.function_call_item(
                    item_id=str(call.get("id") or "") or f"fc_{call_id}",
                    call_id=call_id,
                    name=name,
                    arguments=arguments_json,
                )
            )
            request = ToolExecutionRequest(tool_id=name, arguments=arguments, activity_title=activity_title)
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
                        activity_title=activity_title,
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
