"""Prompt composition and prompted tool execution loops for the CopeNet harness."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol
from uuid import uuid4

from copenet.core.runtime import TurnState
from copenet.providers import Provider, ProviderEvent
from copenet.core.tools import (
    FinalCandidateEnvelope,
    ToolBatchEnvelope,
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolInvocationEnvelope,
    build_openai_tool_schemas,
    build_tool_prompt_section,
    extract_final_candidate,
    extract_tool_batch_invocation,
    extract_tool_invocation,
)

from .planning import HarnessTurnPlan
from .final_gate import FinalGateDecision, final_gate_evaluate


ToolExecutor = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]
TraceRecorder = Callable[[str, dict[str, Any] | None], None]
MAX_TOOL_STEPS = 4
LARGE_TOOL_RESULT_CHAR_LIMIT = 4000


def _tool_call_event_payload(
    *,
    tool_id: str,
    arguments: dict[str, Any],
    step: int,
    channel: str = "tool",
    native: bool = False,
) -> dict[str, Any]:
    hint = None
    for key in ("path", "query", "pattern", "file", "dir", "uri"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            hint = value.strip()
            break
    return {
        "toolId": tool_id,
        "arguments": dict(arguments),
        "target": hint,
        "hint": hint,
        "step": step,
        "channel": channel,
        "native": native,
    }


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


async def collect_provider_turn(
    *,
    provider: Provider,
    prompt: str,
    provider_session_id: str | None,
    abort_event: asyncio.Event,
    model: str | None,
    system_prompt: str | None,
    trace: TraceRecorder | None = None,
    phase: str = "provider",
) -> tuple[list[ProviderEvent], str | None]:
    """Collect one provider turn into memory so the harness can inspect it."""
    events: list[ProviderEvent] = []
    discovered = provider_session_id
    if trace is not None:
        trace(
            "provider_turn_started",
            {
                "phase": phase,
                "providerSessionId": provider_session_id,
            },
        )
    async for event in provider.run(
        prompt=compose_provider_prompt(provider, prompt, system_prompt),
        provider_session_id=provider_session_id,
        abort_event=abort_event,
        model=model,
        system_prompt=provider_system_prompt(provider, system_prompt),
    ):
        if event.provider_session_id:
            discovered = event.provider_session_id
        events.append(event)
        if event.kind == "final":
            break
    if trace is not None:
        trace(
            "provider_turn_completed",
            {
                "phase": phase,
                "providerSessionId": discovered,
                "deltaCount": sum(1 for event in events if event.kind == "delta"),
            },
        )
    return events, discovered


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
    """Run a provider-native tool loop using OpenAI-compatible tool calls."""
    del abort_event  # Native tool turns are non-streaming in v1; keep the signature aligned.
    turn_state = TurnState()
    executed_results: list[ToolExecutionResult] = []
    tool_schemas = build_openai_tool_schemas(plan.tools)
    current_system_prompt = compose_native_tool_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        contract=plan.task_contract,
    )
    messages: list[dict[str, Any]] = []
    if current_system_prompt:
        messages.append({"role": "system", "content": current_system_prompt})
    messages.append({"role": "user", "content": prompt})
    if trace is not None:
        trace("turn_started", turn_state.to_public_dict())

    for step_index in range(MAX_TOOL_STEPS):
        response = await provider.chat_completion(
            messages=messages,
            model=model,
            tools=tool_schemas or None,
        )
        message, finish_reason = _extract_native_choice(response)
        content = _coerce_native_message_content(message.get("content"))
        native_tool_calls = _extract_native_tool_calls(message.get("tool_calls"))
        if trace is not None:
            trace(
                "provider_response_interpreted",
                {
                    "phase": "native",
                    "responseKind": "native_tool_call" if native_tool_calls else "native_final_candidate",
                    "toolCallCount": len(native_tool_calls),
                    "contentLength": len(content),
                    "finishReason": finish_reason,
                },
            )
        if trace is not None:
            trace(
                "provider_turn_completed",
                {
                    "phase": "native-tool-call" if native_tool_calls else "native-final-candidate",
                    "providerSessionId": provider_session_id,
                    "toolCallCount": len(native_tool_calls),
                    "finishReason": finish_reason,
                },
            )

        if native_tool_calls:
            assistant_message: dict[str, Any] = {"role": "assistant", "tool_calls": native_tool_calls}
            if content:
                assistant_message["content"] = content
            messages.append(assistant_message)
            for native_call in native_tool_calls:
                invocation = ToolInvocationEnvelope(
                    tool_id=native_call["function"]["name"],
                    arguments=_parse_native_tool_arguments(native_call["function"].get("arguments")),
                )
                if trace is not None:
                    trace(
                        "tool_requested",
                        {
                            "toolId": invocation.tool_id,
                            "arguments": invocation.arguments,
                            "step": step_index + 1,
                            "native": True,
                        },
                    )
                yield ProviderEvent(
                    kind="meta",
                    metadata={
                        "toolCall": _tool_call_event_payload(
                            tool_id=invocation.tool_id,
                            arguments=invocation.arguments,
                            step=step_index + 1,
                            native=True,
                        ),
                        "turnState": turn_state.to_public_dict(),
                    },
                )
                tool_result = await tool_executor(invocation.to_request(), tool_context)
                tool_result = _with_call_id(tool_result, invocation)
                tool_result = ToolExecutionResult(
                    tool_id=tool_result.tool_id,
                    call_id=native_call.get("id") or tool_result.call_id,
                    channel=tool_result.channel,
                    ok=tool_result.ok,
                    summary=tool_result.summary,
                    body=tool_result.body,
                    output=dict(tool_result.output),
                    error=tool_result.error,
                    artifact_id=tool_result.artifact_id,
                )
                tool_result, artifact_draft = _materialize_tool_result_artifact(
                    tool_result=tool_result,
                    tool_context=tool_context,
                    trace=trace,
                )
                executed_results.append(tool_result)
                turn_state.tool_call_count += 1
                turn_state.record_tool_step(
                    tool_id=tool_result.tool_id,
                    arguments=invocation.arguments,
                    result=tool_result,
                )
                transition_reason = "tool_followup" if tool_result.ok else "tool_error_correction"
                turn_state.queue_input(tool_result.to_runtime_input(), reason=transition_reason)
                meta_payload: dict[str, Any] = {
                    "toolExecution": tool_result.to_event_payload(),
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
                        "tool_call_id": native_call["id"],
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
                        "lastToolId": executed_results[-1].tool_id if executed_results else None,
                    },
                )
            if step_index >= MAX_TOOL_STEPS - 1:
                turn_state.terminal_reason = "max_turns"
                final_answer = await _run_native_terminal_answer(
                    provider=provider,
                    messages=messages,
                    model=model,
                    prompt=prompt,
                    executed_results=executed_results,
                    system_prompt=system_prompt,
                    contract=plan.task_contract,
                )
                if trace is not None:
                    trace(
                        "terminal_answer_forced_after_max_turns",
                        {
                            "path": "native_tool_call",
                            "step": step_index + 1,
                            "toolCount": len(executed_results),
                            "contentLength": len(final_answer),
                        },
                    )
                    trace("turn_completed", turn_state.to_public_dict())
                if final_answer:
                    yield ProviderEvent(kind="delta", text=final_answer)
                yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
                return
            continue

        candidate = _native_final_candidate(
            answer=content,
            turn_state=turn_state,
            contract=plan.task_contract,
        )
        decision = _evaluate_final_candidate(
            plan=plan,
            turn_state=turn_state,
            candidate=candidate,
        )
        if trace is not None:
            trace(
                "final_gate_decision",
                {
                    "ok": True if decision is None else decision.ok,
                    "reasonCode": None if decision is None else decision.reason_code,
                    "missingRequirements": [] if decision is None else list(decision.missing_requirements),
                    "recommendedNextActionType": None if decision is None else decision.recommended_next_action_type,
                    "step": step_index + 1,
                    "native": True,
                },
            )
        if decision is not None and not decision.ok:
            turn_state.register_final_rejection(
                reason_code=decision.reason_code,
                missing_requirements=decision.missing_requirements,
            )
            if trace is not None:
                trace(
                    "final_gate_rejected",
                    {
                        "reasonCode": decision.reason_code,
                        "missingRequirements": decision.missing_requirements,
                        "recommendedNextActionType": decision.recommended_next_action_type,
                        "step": step_index + 1,
                        "native": True,
                    },
                )
                trace("turn_transition", turn_state.to_public_dict())
            if content:
                messages.append({"role": "assistant", "content": content})
            if step_index >= MAX_TOOL_STEPS - 1:
                turn_state.terminal_reason = "max_turns"
                final_answer = await _run_native_terminal_answer(
                    provider=provider,
                    messages=messages,
                    model=model,
                    prompt=prompt,
                    executed_results=executed_results,
                    system_prompt=system_prompt,
                    contract=plan.task_contract,
                )
                if trace is not None:
                    trace(
                        "terminal_answer_forced_after_max_turns",
                        {
                            "path": "native_final_rejection",
                            "step": step_index + 1,
                            "toolCount": len(executed_results),
                            "contentLength": len(final_answer),
                            "reasonCode": decision.reason_code,
                        },
                    )
                    trace("turn_completed", turn_state.to_public_dict())
                if final_answer:
                    yield ProviderEvent(kind="delta", text=final_answer)
                yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
                return
            messages.append(
                {
                    "role": "user",
                    "content": compose_native_tool_follow_up_prompt(
                        user_prompt=prompt,
                        tool_results=executed_results,
                        turn_state=turn_state,
                        contract=plan.task_contract,
                        final_gate_decision=decision,
                    ),
                }
            )
            continue

        turn_state.terminal_reason = "completed"
        if trace is not None:
            trace("turn_completed", turn_state.to_public_dict())
        if content:
            yield ProviderEvent(kind="delta", text=content)
        yield ProviderEvent(kind="final", provider_session_id=provider_session_id)
        return

    if trace is not None:
        turn_state.terminal_reason = "max_turns"
        trace("turn_completed", turn_state.to_public_dict())
    yield ProviderEvent(kind="final", provider_session_id=provider_session_id)


async def run_with_one_tool(
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
    """Run the prompted tool loop with bounded continuation and safe read batches."""
    discovered_provider_session_id = provider_session_id
    executed_results: list[ToolExecutionResult] = []
    turn_state = TurnState()
    current_prompt = compose_tool_attempt_prompt(prompt=prompt, tools=plan.tools, contract=plan.task_contract)
    current_system_prompt = compose_tool_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        tools=plan.tools,
        tool_context=tool_context,
    )
    correction_attempted = False
    last_tool_result: ToolExecutionResult | None = None
    if trace is not None:
        trace("turn_started", turn_state.to_public_dict())

    for step_index in range(MAX_TOOL_STEPS):
        phase = "tool-attempt" if step_index == 0 else "tool-follow-up"
        current_events, discovered_provider_session_id = await collect_provider_turn(
            provider=provider,
            prompt=current_prompt,
            provider_session_id=discovered_provider_session_id,
            abort_event=abort_event,
            model=model,
            system_prompt=current_system_prompt,
            trace=trace,
            phase=phase,
        )
        for event in current_events:
            if event.kind == "meta" and event.provider_session_id:
                yield event

        current_text = "".join(event.text or "" for event in current_events if event.kind == "delta").strip()
        batch_invocation = extract_tool_batch_invocation(current_text) if plan.batch_read_allowed else None
        if batch_invocation is not None:
            if trace is not None:
                trace(
                    "provider_response_interpreted",
                    {
                        "phase": phase,
                        "responseKind": "tool_batch",
                        "toolCallCount": len(batch_invocation.calls),
                        "contentLength": len(current_text),
                    },
                )
            safe_batch, deferred_calls = _split_batch_invocation(batch_invocation, plan.tools)
            if safe_batch is not None:
                if trace is not None:
                    trace(
                        "batch_planned",
                        {
                            "toolIds": [call.tool_id for call in safe_batch.calls],
                            "count": len(safe_batch.calls),
                            "step": step_index + 1,
                        },
                    )
                yield ProviderEvent(
                    kind="meta",
                    metadata={
                        "toolCall": {
                            "toolId": "tool.batch",
                            "arguments": {
                                "calls": [
                                    {
                                        "toolId": call.tool_id,
                                        "arguments": dict(call.arguments),
                                    }
                                    for call in batch_invocation.calls
                                ]
                            },
                            "step": step_index + 1,
                            "channel": "batch",
                            "native": False,
                        },
                        "turnState": turn_state.to_public_dict(),
                    },
                )
                tool_result, artifact_draft = await _run_tool_batch(
                    batch_invocation=safe_batch,
                    tool_executor=tool_executor,
                    tool_context=tool_context,
                    trace=trace,
                )
                batch_members = artifact_draft.pop("batchMembers", []) if artifact_draft is not None else []
                if deferred_calls:
                    tool_result, artifact_draft, batch_members = _attach_deferred_batch_members(
                        tool_result=tool_result,
                        artifact_draft=artifact_draft,
                        batch_members=batch_members,
                        deferred_calls=deferred_calls,
                    )
                    if trace is not None:
                        trace(
                            "tool_batch_split",
                            {
                                "executedToolIds": [call.tool_id for call in safe_batch.calls],
                                "deferredToolIds": [call.tool_id for call in deferred_calls],
                                "step": step_index + 1,
                            },
                        )
                tool_result, persisted_draft = _materialize_tool_result_artifact(
                    tool_result=tool_result,
                    tool_context=tool_context,
                    trace=trace,
                )
                artifact_draft = persisted_draft or artifact_draft
                executed_results.append(tool_result)
                turn_state.tool_call_count += len(batch_invocation.calls)
                for member in batch_members:
                    turn_state.record_tool_step(
                        tool_id=str(member.get("toolId") or "tool.batch"),
                        arguments=dict(member.get("arguments") or {}),
                        result=ToolExecutionResult(
                            tool_id=str(member.get("toolId") or "tool.batch"),
                            call_id=str(member.get("callId") or ""),
                            channel="batch",
                            ok=bool(member.get("ok")),
                            summary=str(member.get("summary") or ""),
                            body=member.get("body"),
                            output=dict(member.get("output") or {}),
                            error=member.get("error"),
                            artifact_id=member.get("artifactId"),
                        ),
                    )
                turn_state.queue_input(tool_result.to_runtime_input(), reason="tool_batch_repair" if deferred_calls else "tool_followup")
                meta_payload: dict[str, Any] = {
                    "toolExecution": tool_result.to_event_payload(),
                    "toolResult": tool_result.to_runtime_input(),
                    "turnState": turn_state.to_public_dict(),
                }
                if artifact_draft is not None:
                    meta_payload["artifactDraft"] = artifact_draft
                yield ProviderEvent(kind="meta", metadata=meta_payload)
                last_tool_result = tool_result
                if step_index >= MAX_TOOL_STEPS - 1:
                    turn_state.terminal_reason = "max_turns"
                    final_events, _ = await collect_provider_turn(
                        provider=provider,
                        prompt=compose_tool_terminal_prompt(
                            user_prompt=prompt,
                            tool_results=executed_results,
                        ),
                        provider_session_id=discovered_provider_session_id,
                        abort_event=abort_event,
                        model=model,
                        system_prompt=compose_system_prompt(
                            provider=provider,
                            system_prompt=system_prompt,
                            extra_instructions="Use the gathered tool results to answer directly. Do not request another tool.",
                        ),
                        trace=trace,
                        phase="tool-final-answer",
                    )
                    for event in final_events:
                        yield event
                    return
                turn_state.drain_pending_input()
                current_prompt = compose_tool_follow_up_prompt(
                    user_prompt=prompt,
                    tool_results=executed_results,
                    turn_state=turn_state,
                    contract=plan.task_contract,
                )
                current_system_prompt = compose_tool_system_prompt(
                    provider=provider,
                    system_prompt=system_prompt,
                    tools=plan.tools,
                    tool_context=tool_context,
                )
                if trace is not None:
                    trace(
                        "tool_loop_continued",
                        {"step": step_index + 1, "lastToolId": tool_result.tool_id, "transitionReason": turn_state.transition_reason},
                    )
                continue

            blocked = _build_correction_result(
                tool_id="tool.batch",
                summary="Tool batch blocked.",
                error="unsafe or unsupported batch request",
                channel="policy",
                body={
                    "results": [_deferred_batch_member(call) for call in batch_invocation.calls],
                    "policyDecision": "unsafe_unknown",
                    "policySummary": "TOOL_BATCH only supports read-only repo/context work. Request writes or shell commands as individual TOOL_CALL actions.",
                },
            )
            executed_results.append(blocked)
            turn_state.tool_call_count += len(batch_invocation.calls)
            turn_state.record_tool_step(tool_id=blocked.tool_id, arguments={}, result=blocked)
            turn_state.queue_input(blocked.to_runtime_input(), reason="tool_batch_repair")
            yield ProviderEvent(
                kind="meta",
                metadata={
                    "toolExecution": blocked.to_event_payload(),
                    "toolResult": blocked.to_runtime_input(),
                    "turnState": turn_state.to_public_dict(),
                },
            )
            if trace is not None:
                trace(
                    "tool_blocked",
                    {
                        "toolId": "tool.batch",
                        "reason": "unsafe or unsupported batch request",
                        "step": step_index + 1,
                        "rawText": current_text[:400],
                    },
                )
                trace(
                    "tool_correction_generated",
                    {
                        "toolId": "tool.batch",
                        "reason": "unsafe or unsupported batch request",
                        "transitionReason": "tool_batch_repair",
                    },
                )
            turn_state.drain_pending_input()
            current_prompt = compose_tool_follow_up_prompt(
                user_prompt=prompt,
                tool_results=executed_results,
                turn_state=turn_state,
                contract=plan.task_contract,
            )
            current_system_prompt = compose_tool_system_prompt(
                provider=provider,
                system_prompt=system_prompt,
                tools=plan.tools,
                tool_context=tool_context,
            )
            continue

        invocation = extract_tool_invocation(current_text)
        final_candidate = extract_final_candidate(current_text)
        if invocation is None and final_candidate is None:
            if trace is not None:
                trace(
                    "provider_response_interpreted",
                    {
                        "phase": phase,
                        "responseKind": "malformed_or_plain_text",
                        "toolCallCount": 0,
                        "contentLength": len(current_text),
                    },
                )
            if current_text and not _looks_like_jsonish_action(current_text) and (
                plan.task_contract is None or bool(turn_state.grounding_actions)
            ):
                final_candidate = _native_final_candidate(
                    answer=current_text,
                    turn_state=turn_state,
                    contract=plan.task_contract,
                )
            else:
                if not correction_attempted:
                    correction_attempted = True
                    correction = _build_correction_result(
                        tool_id="tool.parse",
                        summary="Model action malformed.",
                        error=(
                            "Malformed model action. Emit exactly one legal JSON action: "
                            "TOOL_CALL, TOOL_BATCH, or FINAL_CANDIDATE."
                        ),
                        channel="policy",
                    )
                    executed_results.append(correction)
                    turn_state.queue_input(correction.to_runtime_input(), reason="tool_error_correction")
                    if trace is not None:
                        trace(
                            "tool_correction_generated",
                            {
                                "toolId": "tool.parse",
                                "reason": "malformed model action",
                                "transitionReason": "tool_error_correction",
                            },
                        )
                        trace("turn_transition", turn_state.to_public_dict())
                    yield ProviderEvent(
                        kind="meta",
                        metadata={
                            "toolExecution": correction.to_event_payload(),
                            "toolResult": correction.to_runtime_input(),
                            "turnState": turn_state.to_public_dict(),
                        },
                    )
                    turn_state.drain_pending_input()
                    current_prompt = compose_tool_follow_up_prompt(
                        user_prompt=prompt,
                        tool_results=executed_results,
                        turn_state=turn_state,
                        contract=plan.task_contract,
                    )
                    continue
                if trace is not None:
                    trace(
                        "provider_turn_completed",
                        {
                            "phase": phase,
                            "toolRequested": False,
                            "toolStepCount": len(executed_results),
                        },
                    )
                final_candidate = FinalCandidateEnvelope(
                    answer="Malformed model action after correction.",
                    evidence=[],
                    done_conditions_met=[],
                    remaining_uncertainty=["Model did not emit a legal JSON action."],
                )

        if invocation is None and final_candidate is not None:
            if trace is not None:
                trace(
                    "provider_response_interpreted",
                    {
                        "phase": phase,
                        "responseKind": "final_candidate",
                        "toolCallCount": 0,
                        "contentLength": len(final_candidate.answer),
                    },
                )
            if trace is not None:
                trace(
                    "provider_turn_completed",
                    {
                        "phase": phase,
                        "toolRequested": False,
                        "toolStepCount": len(executed_results),
                        "finalCandidate": True,
                    },
                )
            decision = _evaluate_final_candidate(
                plan=plan,
                turn_state=turn_state,
                candidate=final_candidate,
            )
            if trace is not None:
                trace(
                    "final_gate_decision",
                    {
                        "ok": True if decision is None else decision.ok,
                        "reasonCode": None if decision is None else decision.reason_code,
                        "missingRequirements": [] if decision is None else list(decision.missing_requirements),
                        "recommendedNextActionType": None if decision is None else decision.recommended_next_action_type,
                        "step": step_index + 1,
                        "native": False,
                    },
                )
            if decision is not None and not decision.ok:
                turn_state.register_final_rejection(
                    reason_code=decision.reason_code,
                    missing_requirements=decision.missing_requirements,
                )
                if trace is not None:
                    trace(
                        "final_gate_rejected",
                        {
                            "reasonCode": decision.reason_code,
                            "missingRequirements": decision.missing_requirements,
                            "recommendedNextActionType": decision.recommended_next_action_type,
                            "step": step_index + 1,
                        },
                    )
                    trace("turn_transition", turn_state.to_public_dict())
                turn_state.queue_input(
                    {
                        "type": "final_gate_rejection",
                        "reasonCode": decision.reason_code,
                        "missingRequirements": list(decision.missing_requirements),
                        "recommendedNextAction": decision.recommended_next_action_type,
                    },
                    reason="final_gate_rejected",
                )
                if step_index >= MAX_TOOL_STEPS - 1:
                    turn_state.terminal_reason = "max_turns"
                    final_events, _ = await collect_provider_turn(
                        provider=provider,
                        prompt=compose_tool_terminal_prompt(
                            user_prompt=prompt,
                            tool_results=executed_results,
                        ),
                        provider_session_id=discovered_provider_session_id,
                        abort_event=abort_event,
                        model=model,
                        system_prompt=compose_system_prompt(
                            provider=provider,
                            system_prompt=system_prompt,
                            extra_instructions="Use only the gathered tool results to answer directly. Do not request another tool.",
                        ),
                        trace=trace,
                        phase="tool-final-answer",
                    )
                    if trace is not None:
                        final_text = "".join(event.text or "" for event in final_events if event.kind == "delta").strip()
                        trace(
                            "terminal_answer_forced_after_max_turns",
                            {
                                "path": "prompted_final_rejection",
                                "step": step_index + 1,
                                "toolCount": len(executed_results),
                                "contentLength": len(final_text),
                                "reasonCode": decision.reason_code,
                            },
                        )
                    for event in final_events:
                        yield event
                    return
                turn_state.drain_pending_input()
                current_prompt = compose_tool_follow_up_prompt(
                    user_prompt=prompt,
                    tool_results=executed_results,
                    turn_state=turn_state,
                    contract=plan.task_contract,
                    final_gate_decision=decision,
                )
                current_system_prompt = compose_tool_system_prompt(
                    provider=provider,
                    system_prompt=system_prompt,
                    tools=plan.tools,
                    tool_context=tool_context,
                )
                if trace is not None:
                    trace(
                        "tool_loop_continued",
                        {
                            "step": step_index + 1,
                            "lastToolId": "final_gate",
                            "transitionReason": turn_state.transition_reason,
                        },
                    )
                continue
            if trace is not None:
                turn_state.terminal_reason = "completed"
                trace("turn_completed", turn_state.to_public_dict())
            yield ProviderEvent(kind="delta", text=final_candidate.answer)
            yield ProviderEvent(kind="final", provider_session_id=discovered_provider_session_id)
            return

        if trace is not None:
            trace(
                "provider_response_interpreted",
                {
                    "phase": phase,
                    "responseKind": "tool_call",
                    "toolCallCount": 1,
                    "contentLength": len(current_text),
                    "toolId": invocation.tool_id,
                },
            )
            trace(
                "tool_requested",
                {
                    "toolId": invocation.tool_id,
                    "arguments": invocation.arguments,
                    "step": step_index + 1,
                },
            )

        yield ProviderEvent(
            kind="meta",
            metadata={
                "toolCall": _tool_call_event_payload(
                    tool_id=invocation.tool_id,
                    arguments=invocation.arguments,
                    step=step_index + 1,
                ),
                "turnState": turn_state.to_public_dict(),
            },
        )
        tool_result = await tool_executor(invocation.to_request(), tool_context)
        tool_result = _with_call_id(tool_result, invocation)
        tool_result, artifact_draft = _materialize_tool_result_artifact(
            tool_result=tool_result,
            tool_context=tool_context,
            trace=trace,
        )
        executed_results.append(tool_result)
        turn_state.tool_call_count += 1
        turn_state.record_tool_step(tool_id=tool_result.tool_id, arguments=invocation.arguments, result=tool_result)
        transition_reason = "tool_followup" if tool_result.ok else "tool_error_correction"
        turn_state.queue_input(tool_result.to_runtime_input(), reason=transition_reason)
        meta_payload: dict[str, Any] = {
            "toolExecution": tool_result.to_event_payload(),
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
                },
            )
            trace("turn_transition", turn_state.to_public_dict())
        last_tool_result = tool_result

        if step_index >= MAX_TOOL_STEPS - 1:
            turn_state.terminal_reason = "max_turns"
            final_events, _ = await collect_provider_turn(
                provider=provider,
                prompt=compose_tool_terminal_prompt(
                    user_prompt=prompt,
                    tool_results=executed_results,
                ),
                provider_session_id=discovered_provider_session_id,
                abort_event=abort_event,
                model=model,
                system_prompt=compose_system_prompt(
                    provider=provider,
                    system_prompt=system_prompt,
                    extra_instructions="Use the gathered tool results to answer directly. Do not request another tool.",
                ),
                trace=trace,
                phase="tool-final-answer",
            )
            if trace is not None:
                final_text = "".join(event.text or "" for event in final_events if event.kind == "delta").strip()
                trace(
                    "terminal_answer_forced_after_max_turns",
                    {
                        "path": "prompted_tool_call",
                        "step": step_index + 1,
                        "toolCount": len(executed_results),
                        "contentLength": len(final_text),
                    },
                )
            for event in final_events:
                yield event
            return

        turn_state.drain_pending_input()
        current_prompt = compose_tool_follow_up_prompt(
            user_prompt=prompt,
            tool_results=executed_results,
            turn_state=turn_state,
            contract=plan.task_contract,
        )
        current_system_prompt = compose_tool_system_prompt(
            provider=provider,
            system_prompt=system_prompt,
            tools=plan.tools,
            tool_context=tool_context,
        )
        if trace is not None:
            trace(
                "tool_loop_continued",
                {
                    "step": step_index + 1,
                    "lastToolId": tool_result.tool_id,
                    "transitionReason": turn_state.transition_reason,
                },
            )
    if last_tool_result is not None and trace is not None:
        turn_state.terminal_reason = "tool_error_terminal" if not last_tool_result.ok else "max_turns"
        trace("turn_completed", turn_state.to_public_dict())


def _split_batch_invocation(
    batch: ToolBatchEnvelope,
    tools: list[ToolDescriptor],
) -> tuple[ToolBatchEnvelope | None, list[ToolInvocationEnvelope]]:
    descriptors = {tool.id: tool for tool in tools}
    safe_calls: list[ToolInvocationEnvelope] = []
    deferred_calls: list[ToolInvocationEnvelope] = []
    for call in batch.calls:
        descriptor = descriptors.get(call.tool_id)
        if descriptor is not None and descriptor.category in {"repo-read", "context"}:
            safe_calls.append(call)
        else:
            deferred_calls.append(call)
    return (ToolBatchEnvelope(calls=safe_calls) if safe_calls else None, deferred_calls)


def _deferred_batch_member(call: ToolInvocationEnvelope) -> dict[str, Any]:
    hint = None
    for key in ("path", "query", "pattern", "file", "dir", "command"):
        value = call.arguments.get(key)
        if isinstance(value, str) and value.strip():
            hint = value.strip()
            break
    policy_summary = "TOOL_BATCH only supports read-only repo/context work. Request this tool as an individual TOOL_CALL after the read batch finishes."
    output = {
        "target": hint,
        "policyDecision": "unsafe_unknown",
        "policySummary": policy_summary,
    }
    return {
        "toolId": call.tool_id,
        "ok": False,
        "summary": f"Deferred {call.tool_id}; request it as an individual TOOL_CALL.",
        "output": output,
        "body": output,
        "error": policy_summary,
        "arguments": dict(call.arguments),
    }


def _attach_deferred_batch_members(
    *,
    tool_result: ToolExecutionResult,
    artifact_draft: dict[str, Any] | None,
    batch_members: list[dict[str, Any]],
    deferred_calls: list[ToolInvocationEnvelope],
) -> tuple[ToolExecutionResult, dict[str, Any] | None, list[dict[str, Any]]]:
    if not deferred_calls:
        return tool_result, artifact_draft, batch_members
    body = tool_result.body if isinstance(tool_result.body, dict) else dict(tool_result.output)
    results = list(body.get("results") or []) if isinstance(body, dict) else []
    deferred_members = [_deferred_batch_member(call) for call in deferred_calls]
    results.extend(deferred_members)
    body = dict(body)
    body["results"] = results
    body["policyDecision"] = "unsafe_unknown"
    body["policySummary"] = "TOOL_BATCH only supports read-only repo/context work. Continue remaining writes or shell commands as individual TOOL_CALL actions."
    executed_count = len(batch_members)
    deferred_count = len(deferred_members)
    merged = ToolExecutionResult(
        tool_id=tool_result.tool_id,
        call_id=tool_result.call_id,
        channel=tool_result.channel,
        ok=False,
        summary=f"Executed {executed_count} safe read{'s' if executed_count != 1 else ''}; {deferred_count} remaining tool request{'s' if deferred_count != 1 else ''} must be requested individually.",
        output=body,
        body=body,
        error="mixed batch request repaired",
        artifact_id=tool_result.artifact_id,
    )
    if artifact_draft is not None:
        artifact_draft = dict(artifact_draft)
        artifact_draft["body"] = merged.to_prompt_payload()
        metadata = dict(artifact_draft.get("metadata") or {})
        metadata["deferredToolIds"] = [call.tool_id for call in deferred_calls]
        artifact_draft["metadata"] = metadata
    return merged, artifact_draft, [*batch_members, *deferred_members]


async def _run_tool_batch(
    *,
    batch_invocation: ToolBatchEnvelope,
    tool_executor: ToolExecutor,
    tool_context: ToolExecutionContext,
    trace: TraceRecorder | None,
) -> tuple[ToolExecutionResult, dict[str, Any] | None]:
    requests = batch_invocation.to_requests()
    results = await asyncio.gather(
        *(tool_executor(request, tool_context) for request in requests)
    )
    if trace is not None:
        trace(
            "batch_executed",
            {
                "toolIds": [request.tool_id for request in requests],
                "count": len(results),
                "okCount": sum(1 for result in results if result.ok),
            },
        )
    summary = "; ".join(result.summary for result in results)
    merged_output = {
        "results": [
            {
                "toolId": result.tool_id,
                "ok": result.ok,
                "summary": result.summary,
                "output": result.output,
                "error": result.error,
            }
            for result in results
        ]
    }
    merged = ToolExecutionResult(
        tool_id="tool.batch",
        call_id=f"batch-{uuid4().hex[:10]}",
        channel="batch",
        ok=all(result.ok for result in results),
        summary=summary or f"Executed {len(results)} batched read tools.",
        body=merged_output,
        output=merged_output,
        error=None if all(result.ok for result in results) else "one or more batched tools failed",
    )
    if trace is not None:
        trace(
            "batch_merged",
            {
                "artifactType": "tool_bundle",
                "toolIds": [result.tool_id for result in results],
            },
        )
    artifact_draft = {
        "type": "tool_bundle",
        "title": f"Tool bundle ({len(results)} reads)",
        "body": merged.to_prompt_payload(),
        "metadata": {
            "toolIds": [result.tool_id for result in results],
            "resultCount": len(results),
        },
        "batchMembers": [
            {
                "toolId": result.tool_id,
                "callId": result.call_id,
                "summary": result.summary,
                "body": result.body,
                "output": result.output,
                "error": result.error,
                "artifactId": result.artifact_id,
                "ok": result.ok,
                "arguments": request.arguments,
            }
            for request, result in zip(requests, results, strict=False)
        ],
    }
    return merged, artifact_draft


def _extract_native_choice(response: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("LM Studio returned no choices for native tool completion.")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RuntimeError("LM Studio returned an invalid native tool choice payload.")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("LM Studio returned no assistant message for native tool completion.")
    finish_reason = choice.get("finish_reason")
    return message, str(finish_reason).strip() if finish_reason is not None else None


def _coerce_native_message_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _extract_native_tool_calls(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        call_id = str(item.get("id") or "").strip() or f"call-{uuid4().hex[:10]}"
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": function.get("arguments"),
                },
            }
        )
    return rows


def _parse_native_tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _native_tool_message_content(tool_result: ToolExecutionResult) -> str:
    body = tool_result.body if tool_result.body is not None else tool_result.output
    if isinstance(body, str):
        return body
    return json.dumps(body, ensure_ascii=False, indent=2)


def _looks_like_jsonish_action(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.startswith("{") or stripped.startswith("[") or stripped.startswith("```"):
        return True
    return any(token in stripped for token in ['"tool', '"state"', "tool_calls", "tool_id"])


def _extract_cited_evidence(answer: str, visited_paths: list[str]) -> list[str]:
    lowered_answer = answer.lower()
    basename_map: dict[str, list[str]] = {}
    cited: list[str] = []
    for path in visited_paths:
        normalized = str(path).strip()
        if not normalized:
            continue
        basename = normalized.rsplit("/", 1)[-1].lower()
        basename_map.setdefault(basename, []).append(normalized)
        if normalized.lower() in lowered_answer and normalized not in cited:
            cited.append(normalized)
    for basename, paths in basename_map.items():
        if len(paths) == 1 and basename in lowered_answer and paths[0] not in cited:
            cited.append(paths[0])
    return cited


def _native_final_candidate(
    *,
    answer: str,
    turn_state: TurnState,
    contract: Any | None,
) -> FinalCandidateEnvelope:
    ledger = turn_state.evidence_ledger
    visited_paths = list(ledger.get("visitedPaths") or [])
    cited_paths = _extract_cited_evidence(answer, visited_paths)
    if not cited_paths and len(visited_paths) == 1 and turn_state.grounding_actions:
        cited_paths = [visited_paths[0]]
    done_conditions = list(getattr(contract, "done_conditions", []) or []) if contract is not None else []
    return FinalCandidateEnvelope(
        answer=answer.strip() or "No grounded final answer was produced.",
        evidence=cited_paths,
        done_conditions_met=cited_paths and done_conditions or [],
        remaining_uncertainty=[],
    )


async def _run_native_terminal_answer(
    *,
    provider: NativeToolProvider,
    messages: list[dict[str, Any]],
    model: str | None,
    prompt: str,
    executed_results: list[ToolExecutionResult],
    system_prompt: str | None,
    contract: Any | None,
) -> str:
    final_messages = list(messages)
    final_messages.append(
        {
            "role": "user",
            "content": compose_native_terminal_prompt(
                user_prompt=prompt,
                tool_results=executed_results,
                contract=contract,
            ),
        }
    )
    response = await provider.chat_completion(
        messages=final_messages,
        model=model,
        tools=None,
    )
    message, _ = _extract_native_choice(response)
    content = _coerce_native_message_content(message.get("content"))
    if content:
        return content
    if executed_results:
        return executed_results[-1].summary
    return ""


def compose_tool_attempt_prompt(*, prompt: str, tools: list[ToolDescriptor], contract: Any | None = None) -> str:
    contract_block = ""
    if contract is not None:
        contract_block = (
            "Current contract:\n"
            f"- Goal: {getattr(contract, 'goal', '')}\n"
            f"- Task kind: {getattr(contract, 'task_kind', '')}\n"
            f"- Required evidence: {', '.join(getattr(contract, 'required_evidence', []) or []) or '(none)'}\n"
            f"- Done conditions: {', '.join(getattr(contract, 'done_conditions', []) or []) or '(none)'}\n\n"
        )
    return (
        "User request:\n"
        f"{prompt}\n\n"
        f"{contract_block}"
        "Decide whether you need tools before answering. "
        "Respond with exactly one legal JSON action: TOOL_CALL, TOOL_BATCH, or FINAL_CANDIDATE.\n"
        "For repository inspection, directory listing alone is rarely enough. "
        "Prefer direct evidence from files.read or directional discovery from files.rg before summarizing. "
        "Use context.prepare only for orientation, not as a substitute for inspecting files."
        "\nRepeated shallow reconnaissance is a bad stop point. If you already used files.list or context.prepare, your next action should usually be files.rg or files.read."
        "\nBefore answering a repository-architecture or setup question, gather evidence from meaningful files and be ready to cite the specific files you inspected."
        "\nIf you infer a file path instead of receiving it explicitly from the user, verify it exists with files.rg or files.list before calling files.read."
        "\nDo not call files.read on directories; use files.list for directories and files.rg for broader exploration."
        "\nAvoid shell pipelines or command chaining in shell.exec. Prefer files.rg, files.read, or simple single commands."
        f"\n\n{build_tool_prompt_section(tools)}"
    )


def compose_native_tool_follow_up_prompt(
    *,
    user_prompt: str,
    tool_results: list[ToolExecutionResult],
    turn_state: TurnState,
    contract: Any | None = None,
    final_gate_decision: FinalGateDecision | None = None,
) -> str:
    contract_block = ""
    if contract is not None:
        contract_block = (
            "Current contract:\n"
            f"- Goal: {getattr(contract, 'goal', '')}\n"
            f"- Task kind: {getattr(contract, 'task_kind', '')}\n"
            f"- Allowed tools: {', '.join(getattr(contract, 'allowed_tools', []) or []) or '(none)'}\n"
            f"- Required evidence: {', '.join(getattr(contract, 'required_evidence', []) or []) or '(none)'}\n"
            f"- Done conditions: {', '.join(getattr(contract, 'done_conditions', []) or []) or '(none)'}\n\n"
        )
    ledger = turn_state.evidence_ledger
    rejection_block = ""
    if final_gate_decision is not None and not final_gate_decision.ok:
        rejection_block = (
            "You are not done yet. Missing requirements:\n"
            + "\n".join(f"- {item}" for item in final_gate_decision.missing_requirements)
            + "\n"
            + f"Recommended next action type: {final_gate_decision.recommended_next_action_type or 'tool'}\n\n"
        )
    shallow_recon = _shallow_reconnaissance_nudge(turn_state)
    return (
        "Original user request:\n"
        f"{user_prompt}\n\n"
        f"{contract_block}"
        f"{rejection_block}"
        "Tool results gathered so far:\n"
        f"{_tool_results_payload(tool_results)}\n\n"
        "Ledger snapshot:\n"
        f"- Visited tools: {', '.join(ledger.get('visitedTools') or []) or '(none)'}\n"
        f"- Visited paths: {', '.join(ledger.get('visitedPaths') or []) or '(none)'}\n"
        f"- Grounding actions: {', '.join(ledger.get('groundingActions') or []) or '(none)'}\n"
        f"- Last tool summary: {ledger.get('lastToolResultSummary') or '(none)'}\n\n"
        f"{shallow_recon}"
        "Continue by using the available native tools if evidence is still missing. "
        "Do not finalize until your answer cites the grounded files you inspected. "
        "Use context.prepare only for overview; repository claims need direct file evidence."
    )


def compose_tool_follow_up_prompt(
    *,
    user_prompt: str,
    tool_results: list[ToolExecutionResult],
    turn_state: TurnState,
    contract: Any | None = None,
    final_gate_decision: FinalGateDecision | None = None,
) -> str:
    corrective_line = ""
    if turn_state.transition_reason == "tool_error_correction":
        corrective_line = (
            "\nThe previous tool request failed validation, policy, or execution. "
            "Repair the tool call directly if another tool is still needed.\n"
        )
    elif turn_state.transition_reason == "tool_batch_repair":
        corrective_line = (
            "\nThe previous TOOL_BATCH mixed read-only work with writes or shell commands. "
            "Use TOOL_BATCH only for read-only repo/context work, then continue remaining edits or shell commands as individual TOOL_CALL actions.\n"
        )
    contract_block = ""
    if contract is not None:
        contract_block = (
            f"Current contract:\n"
            f"- Goal: {getattr(contract, 'goal', '')}\n"
            f"- Task kind: {getattr(contract, 'task_kind', '')}\n"
            f"- Allowed tools: {', '.join(getattr(contract, 'allowed_tools', []) or []) or '(none)'}\n"
            f"- Required evidence: {', '.join(getattr(contract, 'required_evidence', []) or []) or '(none)'}\n"
            f"- Done conditions: {', '.join(getattr(contract, 'done_conditions', []) or []) or '(none)'}\n\n"
        )
    ledger = turn_state.evidence_ledger
    ledger_block = (
        "Ledger snapshot:\n"
        f"- Visited tools: {', '.join(ledger.get('visitedTools') or []) or '(none)'}\n"
        f"- Visited paths: {', '.join(ledger.get('visitedPaths') or []) or '(none)'}\n"
        f"- Grounding actions: {', '.join(ledger.get('groundingActions') or []) or '(none)'}\n"
        f"- Last tool summary: {ledger.get('lastToolResultSummary') or '(none)'}\n"
    )
    rejection_block = ""
    if final_gate_decision is not None and not final_gate_decision.ok:
        rejection_block = (
            "Missing requirements:\n"
            + "\n".join(f"- {item}" for item in final_gate_decision.missing_requirements)
            + "\n"
        )
    shallow_recon = _shallow_reconnaissance_nudge(turn_state)
    return (
        "Original user request:\n"
        f"{user_prompt}\n\n"
        f"{contract_block}"
        "Tool results gathered so far:\n"
        f"{_tool_results_payload(tool_results)}\n\n"
        f"{ledger_block}\n"
        f"{rejection_block}"
        f"Current transition reason: {turn_state.transition_reason}\n"
        f"Pending follow-up inputs: {len(turn_state.pending_input)}\n"
        f"{shallow_recon}"
        "Respond with exactly one legal JSON action: TOOL_CALL, TOOL_BATCH, or FINAL_CANDIDATE.\n"
        "For repository exploration, a plain files.list result usually is not enough evidence to stop. "
        "Prefer a follow-up files.rg or files.read step unless the user asked only for a directory listing. "
        "Use context.prepare for orientation only."
        "\nBefore answering a repository-architecture or setup question, gather evidence from meaningful files and cite the specific files you inspected."
        "\nIf you infer a file path instead of receiving it explicitly from the user, verify it exists with files.rg or files.list before calling files.read."
        "\nUse write tools only if they are listed in the capability manifest. If write tools are unavailable, continue with read/shell/artifact tools and explain the limitation honestly."
        "\nWhen a task mixes read, edit, shell, and artifact work, prefer the sequence inspect -> edit/write -> verify -> artifact."
        "\nDo not use files.read on directories. Avoid shell.exec pipelines or chained shell commands."
        f"{corrective_line}"
    )


def compose_native_terminal_prompt(
    *,
    user_prompt: str,
    tool_results: list[ToolExecutionResult],
    contract: Any | None = None,
) -> str:
    contract_rules = ""
    if contract is not None:
        contract_rules = (
            "Answer rules:\n"
            + "\n".join(f"- {rule}" for rule in getattr(contract, "final_answer_rules", []) or [])
            + "\n\n"
        )
    return (
        "Original user request:\n"
        f"{user_prompt}\n\n"
        f"{contract_rules}"
        "Tool results gathered:\n"
        f"{_tool_results_payload(tool_results)}\n\n"
        "Answer directly using only the gathered evidence. Cite the files you inspected in the answer. "
        "Do not request more tools."
    )


def compose_tool_terminal_prompt(*, user_prompt: str, tool_results: list[ToolExecutionResult]) -> str:
    return (
        "Original user request:\n"
        f"{user_prompt}\n\n"
        "Tool results gathered:\n"
        f"{_tool_results_payload(tool_results)}\n\n"
        "Return exactly one FINAL_CANDIDATE JSON object using these results. "
        "Do not request another tool and do not emit prose outside JSON."
    )


def compose_tool_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
    tools: list[ToolDescriptor],
    tool_context: ToolExecutionContext,
) -> str | None:
    return compose_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        extra_instructions=build_tool_prompt_section(tools, context=tool_context),
    )


def compose_native_tool_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
    contract: Any | None = None,
) -> str | None:
    contract_lines: list[str] = []
    if contract is not None:
        contract_lines.extend(
            [
                f"Current goal: {getattr(contract, 'goal', '')}",
                f"Task kind: {getattr(contract, 'task_kind', '')}",
            ]
        )
        required = getattr(contract, "required_evidence", []) or []
        done = getattr(contract, "done_conditions", []) or []
        if required:
            contract_lines.append(f"Required evidence: {', '.join(required)}")
        if done:
            contract_lines.append(f"Done conditions: {', '.join(done)}")
    extra = (
        "Use the provider-native tools when evidence is missing. "
        "For repository and coding questions, directory names and conventions are not enough proof. "
        "Inspect relevant files, then cite the specific files you used in the final answer. "
        "If you are missing evidence, continue with another tool call instead of guessing. "
        "Use context.prepare for orientation only, and escalate away from repeated files.list toward files.rg or files.read."
    )
    if contract_lines:
        extra = extra + "\n\n" + "\n".join(contract_lines)
    return compose_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        extra_instructions=extra,
    )


def _tool_results_payload(tool_results: list[ToolExecutionResult]) -> str:
    return "\n\n".join(result.to_prompt_payload() for result in tool_results)


def _evaluate_final_candidate(
    *,
    plan: HarnessTurnPlan,
    turn_state: TurnState,
    candidate: FinalCandidateEnvelope,
) -> FinalGateDecision | None:
    if plan.task_contract is None:
        return None
    return final_gate_evaluate(
        contract=plan.task_contract,
        turn_state=turn_state,
        candidate=candidate,
    )


def _build_correction_result(
    *,
    tool_id: str,
    summary: str,
    error: str,
    channel: str,
    body: dict[str, Any] | None = None,
) -> ToolExecutionResult:
    payload = dict(body or {"error": error})
    if "error" not in payload:
        payload["error"] = error
    return ToolExecutionResult(
        tool_id=tool_id,
        call_id=f"correction-{uuid4().hex[:10]}",
        channel=channel,
        ok=False,
        summary=summary,
        body=payload,
        output=dict(payload),
        error=error,
    )


def _with_call_id(
    result: ToolExecutionResult,
    invocation: ToolInvocationEnvelope,
) -> ToolExecutionResult:
    if result.call_id:
        return result
    return ToolExecutionResult(
        tool_id=result.tool_id,
        call_id=f"{invocation.tool_id}-{uuid4().hex[:10]}",
        channel=result.channel,
        ok=result.ok,
        summary=result.summary,
        body=result.body,
        output=dict(result.output),
        error=result.error,
        artifact_id=result.artifact_id,
    )


def _materialize_tool_result_artifact(
    *,
    tool_result: ToolExecutionResult,
    tool_context: ToolExecutionContext,
    trace: TraceRecorder | None,
) -> tuple[ToolExecutionResult, dict[str, Any] | None]:
    body = tool_result.body if tool_result.body is not None else tool_result.output
    payload_text = json.dumps(body, ensure_ascii=False, indent=2) if not isinstance(body, str) else body
    if not payload_text.strip():
        normalized = ToolExecutionResult(
            tool_id=tool_result.tool_id,
            call_id=tool_result.call_id,
            channel=tool_result.channel,
            ok=tool_result.ok,
            summary=tool_result.summary,
            body=f"({tool_result.tool_id} completed with no output)",
            output=dict(tool_result.output),
            error=tool_result.error,
            artifact_id=tool_result.artifact_id,
        )
        return normalized, None
    if len(payload_text) <= LARGE_TOOL_RESULT_CHAR_LIMIT or tool_context.artifact_store is None or not tool_context.session_key:
        if trace is not None and tool_result.call_id:
            trace(
                "tool_result_normalized",
                {
                    "toolId": tool_result.tool_id,
                    "callId": tool_result.call_id,
                    "channel": tool_result.channel,
                    "success": tool_result.ok,
                },
            )
        return tool_result, None

    artifact = tool_context.artifact_store.create(
        session_key=tool_context.session_key,
        run_id=tool_result.call_id or f"tool-{uuid4().hex[:8]}",
        artifact_type="tool_output",
        title=f"{tool_result.tool_id} output",
        body=payload_text,
        metadata={
            "toolId": tool_result.tool_id,
            "callId": tool_result.call_id,
            "channel": tool_result.channel,
            "persistedOutput": True,
        },
    )
    preview = payload_text[:280].strip()
    if len(payload_text) > 280:
        preview += "..."
    persisted_body = {
        "artifactId": artifact.artifact_id,
        "preview": preview,
        "persistedOutput": True,
    }
    persisted = ToolExecutionResult(
        tool_id=tool_result.tool_id,
        call_id=tool_result.call_id,
        channel=tool_result.channel,
        ok=tool_result.ok,
        summary=tool_result.summary,
        body=persisted_body,
        output=dict(tool_result.output),
        error=tool_result.error,
        artifact_id=artifact.artifact_id,
    )
    if trace is not None:
        trace(
            "tool_result_persisted",
            {
                "toolId": tool_result.tool_id,
                "callId": tool_result.call_id,
                "artifactId": artifact.artifact_id,
            },
        )
    return persisted, None


def compose_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
    extra_instructions: str | None = None,
) -> str | None:
    parts = [part.strip() for part in (system_prompt or "", extra_instructions or "") if part and part.strip()]
    if not parts:
        return None
    return "\n\n".join(parts)


def compose_interaction_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
    plan: HarnessTurnPlan,
) -> str | None:
    extra = _interaction_instructions(plan)
    return compose_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        extra_instructions=extra,
    )


def _interaction_instructions(plan: HarnessTurnPlan) -> str:
    if plan.interaction_class == "casual":
        return (
            "Be warm and conversational by default. "
            "Do not foreground harness machinery, tool protocol, or repo inspection unless the user clearly asks for action."
        )
    if plan.interaction_class == "advisory":
        return (
            "Be structured but conversational. "
            "Do not imply you inspected the repo unless you actually did. "
            "If inspection would improve confidence, say so briefly instead of jumping into tools automatically."
        )
    if plan.interaction_class == "risky":
        return (
            "Treat this as an action-heavy turn. Use tools carefully, ground non-trivial claims, and surface caution around risky or irreversible actions."
        )
    return (
        "Treat this as an action-oriented turn. Use tools when they materially help, read/search before editing, and ground non-trivial repo claims in specific files."
    )


def _shallow_reconnaissance_nudge(turn_state: TurnState) -> str:
    shallow_count = sum(
        1 for item in turn_state.evidence_items if item.get("category") in {"reconnaissance", "contextual"}
    )
    if shallow_count < 2 or turn_state.grounding_actions:
        return ""
    return (
        "Shallow reconnaissance saturation: you already used files.list/context.prepare without direct file evidence. "
        "Your next step should usually be files.rg or files.read, not another shallow overview.\n"
    )


def provider_system_prompt(provider: Provider, system_prompt: str | None) -> str | None:
    if getattr(provider, "name", "") == "codex-cli":
        return None
    return system_prompt


def compose_provider_prompt(provider: Provider, prompt: str, system_prompt: str | None) -> str:
    if getattr(provider, "name", "") != "codex-cli" or not system_prompt:
        return prompt
    return (
        "System instructions:\n"
        f"{system_prompt}\n\n"
        "User request:\n"
        f"{prompt}"
    )
