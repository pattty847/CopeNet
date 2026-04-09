"""Prompt composition and one-tool execution loop for the CopeNet harness."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Awaitable, Callable

from copenet.providers import Provider, ProviderEvent
from copenet.core.tools import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    build_tool_prompt_section,
    extract_tool_invocation,
)

from .planning import HarnessTurnPlan


ToolExecutor = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]
TraceRecorder = Callable[[str, dict[str, Any] | None], None]


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
    """Run the one-tool loop for models that need prompted tool use."""
    first_prompt = compose_tool_attempt_prompt(prompt=prompt, tools=plan.tools)
    first_system_prompt = compose_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        extra_instructions=build_tool_prompt_section(plan.tools),
    )
    first_events, discovered_provider_session_id = await collect_provider_turn(
        provider=provider,
        prompt=first_prompt,
        provider_session_id=provider_session_id,
        abort_event=abort_event,
        model=model,
        system_prompt=first_system_prompt,
        trace=trace,
        phase="tool-attempt",
    )
    for event in first_events:
        if event.kind == "meta" and event.provider_session_id:
            yield event

    first_text = "".join(event.text or "" for event in first_events if event.kind == "delta").strip()
    invocation = extract_tool_invocation(first_text)
    if invocation is None:
        if trace is not None:
            trace(
                "provider_turn_completed",
                {
                    "phase": "tool-attempt",
                    "toolRequested": False,
                },
            )
        for event in first_events:
            if event.kind != "meta":
                yield event
        return

    if trace is not None:
        trace(
            "tool_requested",
            {
                "toolId": invocation.tool_id,
                "arguments": invocation.arguments,
            },
        )

    tool_result = await tool_executor(invocation.to_request(), tool_context)
    yield ProviderEvent(kind="meta", metadata={"toolExecution": tool_result.to_event_payload()})

    second_events, _ = await collect_provider_turn(
        provider=provider,
        prompt=compose_tool_follow_up_prompt(user_prompt=prompt, tool_result=tool_result),
        provider_session_id=discovered_provider_session_id,
        abort_event=abort_event,
        model=model,
        system_prompt=compose_system_prompt(
            provider=provider,
            system_prompt=system_prompt,
            extra_instructions="Use the tool result to answer the user directly. Do not request another tool.",
        ),
        trace=trace,
        phase="tool-follow-up",
    )
    for event in second_events:
        yield event


def compose_tool_attempt_prompt(*, prompt: str, tools: list[ToolDescriptor]) -> str:
    return (
        "User request:\n"
        f"{prompt}\n\n"
        "Decide whether you need exactly one tool before answering. "
        "If needed, respond only with the JSON tool invocation."
        f"\n\n{build_tool_prompt_section(tools)}"
    )


def compose_tool_follow_up_prompt(*, user_prompt: str, tool_result: ToolExecutionResult) -> str:
    return (
        "Original user request:\n"
        f"{user_prompt}\n\n"
        "Tool result:\n"
        f"{tool_result.to_prompt_payload()}\n\n"
        "Answer the user directly using the tool result. "
        "If the tool result is insufficient, say what is still missing."
    )


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
