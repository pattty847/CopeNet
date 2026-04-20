"""Prompt composition and prompted tool execution loops for the CopeNet harness."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Awaitable, Callable
from uuid import uuid4

from copenet.core.runtime import TurnState
from copenet.providers import Provider, ProviderEvent
from copenet.core.tools import (
    ToolBatchEnvelope,
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    ToolInvocationEnvelope,
    build_tool_prompt_section,
    extract_tool_batch_invocation,
    extract_tool_invocation,
)

from .planning import HarnessTurnPlan


ToolExecutor = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]
TraceRecorder = Callable[[str, dict[str, Any] | None], None]
MAX_TOOL_STEPS = 3
LARGE_TOOL_RESULT_CHAR_LIMIT = 4000


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
    current_prompt = compose_tool_attempt_prompt(prompt=prompt, tools=plan.tools)
    current_system_prompt = compose_tool_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        tools=plan.tools,
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
            if _is_safe_batch(batch_invocation, plan.tools):
                if trace is not None:
                    trace(
                        "batch_planned",
                        {
                            "toolIds": [call.tool_id for call in batch_invocation.calls],
                            "count": len(batch_invocation.calls),
                            "step": step_index + 1,
                        },
                    )
                tool_result, artifact_draft = await _run_tool_batch(
                    batch_invocation=batch_invocation,
                    tool_executor=tool_executor,
                    tool_context=tool_context,
                    trace=trace,
                )
                tool_result, persisted_draft = _materialize_tool_result_artifact(
                    tool_result=tool_result,
                    tool_context=tool_context,
                    trace=trace,
                )
                artifact_draft = persisted_draft or artifact_draft
                executed_results.append(tool_result)
                turn_state.tool_call_count += len(batch_invocation.calls)
                turn_state.queue_input(tool_result.to_runtime_input(), reason="tool_followup")
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
                )
                current_system_prompt = compose_tool_system_prompt(
                    provider=provider,
                    system_prompt=system_prompt,
                    tools=plan.tools,
                )
                if trace is not None:
                    trace(
                        "tool_loop_continued",
                        {"step": step_index + 1, "lastToolId": tool_result.tool_id},
                    )
                continue

            blocked = _build_correction_result(
                tool_id="tool.batch",
                summary="Tool batch blocked.",
                error="unsafe or unsupported batch request",
                channel="policy",
            )
            executed_results.append(blocked)
            turn_state.tool_call_count += 1
            turn_state.queue_input(blocked.to_runtime_input(), reason="tool_error_correction")
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
                        "transitionReason": "tool_error_correction",
                    },
                )
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
                    extra_instructions="Use the tool result to answer directly. Do not request another tool.",
                ),
                trace=trace,
                phase="tool-final-answer",
            )
            for event in final_events:
                yield event
            return

        invocation = extract_tool_invocation(current_text)
        if invocation is None:
            if _looks_like_tool_attempt(current_text) and not correction_attempted:
                correction_attempted = True
                correction = _build_correction_result(
                    tool_id="tool.parse",
                    summary="Tool request malformed.",
                    error="Malformed tool request. Emit only one valid JSON tool invocation or one valid tool_calls batch.",
                    channel="policy",
                )
                executed_results.append(correction)
                turn_state.queue_input(correction.to_runtime_input(), reason="tool_error_correction")
                if trace is not None:
                    trace(
                        "tool_correction_generated",
                        {
                            "toolId": "tool.parse",
                            "reason": "malformed tool request",
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
                turn_state.terminal_reason = "completed"
                trace("turn_completed", turn_state.to_public_dict())
            for event in current_events:
                if event.kind != "meta":
                    yield event
            return

        if trace is not None:
            trace(
                "tool_requested",
                {
                    "toolId": invocation.tool_id,
                    "arguments": invocation.arguments,
                    "step": step_index + 1,
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
            for event in final_events:
                yield event
            return

        turn_state.drain_pending_input()
        current_prompt = compose_tool_follow_up_prompt(
            user_prompt=prompt,
            tool_results=executed_results,
            turn_state=turn_state,
        )
        current_system_prompt = compose_tool_system_prompt(
            provider=provider,
            system_prompt=system_prompt,
            tools=plan.tools,
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


def _is_safe_batch(batch: ToolBatchEnvelope, tools: list[ToolDescriptor]) -> bool:
    descriptors = {tool.id: tool for tool in tools}
    if len(batch.calls) < 2:
        return False
    for call in batch.calls:
        descriptor = descriptors.get(call.tool_id)
        if descriptor is None:
            return False
        if descriptor.category not in {"repo-read", "context"}:
            return False
    return True


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
    }
    return merged, artifact_draft


def compose_tool_attempt_prompt(*, prompt: str, tools: list[ToolDescriptor]) -> str:
    return (
        "User request:\n"
        f"{prompt}\n\n"
        "Decide whether you need tools before answering. "
        "If needed, respond only with the JSON tool invocation or a safe read-only batch.\n"
        "For repository inspection, directory listing alone is rarely enough. "
        "Prefer at least one relevant files.read, files.search, or context.prepare step before summarizing."
        "\nBefore answering a repository-architecture or setup question, gather evidence from meaningful files and be ready to cite the specific files you inspected."
        "\nDo not call files.read on directories; use files.list for directories and files.search for broader exploration."
        "\nAvoid shell pipelines or command chaining in shell.exec. Prefer files.search, context.prepare, or simple single commands."
        f"\n\n{build_tool_prompt_section(tools)}"
    )


def compose_tool_follow_up_prompt(
    *,
    user_prompt: str,
    tool_results: list[ToolExecutionResult],
    turn_state: TurnState,
) -> str:
    corrective_line = ""
    if turn_state.transition_reason == "tool_error_correction":
        corrective_line = (
            "\nThe previous tool request failed validation, policy, or execution. "
            "Repair the tool call directly if another tool is still needed.\n"
        )
    return (
        "Original user request:\n"
        f"{user_prompt}\n\n"
        "Tool results gathered so far:\n"
        f"{_tool_results_payload(tool_results)}\n\n"
        f"Current transition reason: {turn_state.transition_reason}\n"
        f"Pending follow-up inputs: {len(turn_state.pending_input)}\n"
        "Decide whether one more tool or one safe read-only batch is still needed. "
        "If another tool is needed, respond only with the JSON invocation shape. "
        "If you already have enough information, answer the user directly.\n"
        "For repository exploration, a plain files.list result usually is not enough evidence to stop. "
        "Prefer a follow-up files.read, files.search, or context.prepare step unless the user asked only for a directory listing."
        "\nBefore answering a repository-architecture or setup question, gather evidence from meaningful files and cite the specific files you inspected."
        "\nDo not use files.read on directories. Avoid shell.exec pipelines or chained shell commands."
        f"{corrective_line}"
    )


def compose_tool_terminal_prompt(*, user_prompt: str, tool_results: list[ToolExecutionResult]) -> str:
    return (
        "Original user request:\n"
        f"{user_prompt}\n\n"
        "Tool results gathered:\n"
        f"{_tool_results_payload(tool_results)}\n\n"
        "Answer the user directly using these results. "
        "Do not request another tool."
    )


def compose_tool_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
    tools: list[ToolDescriptor],
) -> str | None:
    return compose_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        extra_instructions=build_tool_prompt_section(tools),
    )


def _tool_results_payload(tool_results: list[ToolExecutionResult]) -> str:
    return "\n\n".join(result.to_prompt_payload() for result in tool_results)


def _looks_like_tool_attempt(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if "tool_id" in stripped or "tool_calls" in stripped or "toolCalls" in stripped:
        return True
    return stripped.startswith("{") and stripped.endswith("}")


def _build_correction_result(
    *,
    tool_id: str,
    summary: str,
    error: str,
    channel: str,
) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_id=tool_id,
        call_id=f"correction-{uuid4().hex[:10]}",
        channel=channel,
        ok=False,
        summary=summary,
        body={"error": error},
        output={"error": error},
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
