"""Prompt composition and prompted tool execution loops for the CopeNet harness."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Awaitable, Callable

from copenet.providers import Provider, ProviderEvent
from copenet.core.tools import (
    ToolBatchEnvelope,
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    build_tool_prompt_section,
    extract_tool_batch_invocation,
    extract_tool_invocation,
)

from .planning import HarnessTurnPlan


ToolExecutor = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]
TraceRecorder = Callable[[str, dict[str, Any] | None], None]
BATCHABLE_TOOL_IDS = {"files.list", "files.read", "files.search", "context.prepare"}
MAX_TOOL_STEPS = 3


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
    current_prompt = compose_tool_attempt_prompt(prompt=prompt, tools=plan.tools)
    current_system_prompt = compose_tool_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        tools=plan.tools,
    )

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
                executed_results.append(tool_result)
                meta_payload: dict[str, Any] = {"toolExecution": tool_result.to_event_payload()}
                if artifact_draft is not None:
                    meta_payload["artifactDraft"] = artifact_draft
                yield ProviderEvent(kind="meta", metadata=meta_payload)
                if step_index >= MAX_TOOL_STEPS - 1:
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
                current_prompt = compose_tool_follow_up_prompt(
                    user_prompt=prompt,
                    tool_results=executed_results,
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

            blocked = ToolExecutionResult(
                tool_id="tool.batch",
                ok=False,
                summary="Tool batch blocked.",
                error="unsafe or unsupported batch request",
            )
            executed_results.append(blocked)
            yield ProviderEvent(kind="meta", metadata={"toolExecution": blocked.to_event_payload()})
            if trace is not None:
                trace(
                    "tool_blocked",
                    {
                        "toolId": "tool.batch",
                        "reason": "unsafe or unsupported batch request",
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
            if trace is not None:
                trace(
                    "provider_turn_completed",
                    {
                        "phase": phase,
                        "toolRequested": False,
                        "toolStepCount": len(executed_results),
                    },
                )
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
        executed_results.append(tool_result)
        yield ProviderEvent(kind="meta", metadata={"toolExecution": tool_result.to_event_payload()})

        if step_index >= MAX_TOOL_STEPS - 1:
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

        current_prompt = compose_tool_follow_up_prompt(
            user_prompt=prompt,
            tool_results=executed_results,
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


def _is_safe_batch(batch: ToolBatchEnvelope, tools: list[ToolDescriptor]) -> bool:
    descriptors = {tool.id: tool for tool in tools}
    if len(batch.calls) < 2:
        return False
    for call in batch.calls:
        descriptor = descriptors.get(call.tool_id)
        if descriptor is None:
            return False
        if descriptor.id not in BATCHABLE_TOOL_IDS:
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
        ok=all(result.ok for result in results),
        summary=summary or f"Executed {len(results)} batched read tools.",
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
        "If needed, respond only with the JSON tool invocation or a safe read-only batch."
        f"\n\n{build_tool_prompt_section(tools)}"
    )


def compose_tool_follow_up_prompt(*, user_prompt: str, tool_results: list[ToolExecutionResult]) -> str:
    return (
        "Original user request:\n"
        f"{user_prompt}\n\n"
        "Tool results gathered so far:\n"
        f"{_tool_results_payload(tool_results)}\n\n"
        "Decide whether one more tool or one safe read-only batch is still needed. "
        "If another tool is needed, respond only with the JSON invocation shape. "
        "If you already have enough information, answer the user directly."
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
