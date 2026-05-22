"""CopeNet-native harness abstractions and one-step tool loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from typing import AsyncIterator, Callable

from copenet.providers import Provider, ProviderEvent
from copenet.core.tools import ToolDescriptor, ToolExecutionContext

from .capabilities import ModelCapabilityProfile
from .decision import resolve_harness_decision_record
from .planning import HarnessTurnPlan, TraceRecorder, plan_turn
from .tool_loop import (
    ToolExecutor,
    collect_provider_turn,
    compose_provider_prompt,
    provider_system_prompt,
    run_with_prompted_tools,
    run_with_native_tools,
)


@dataclass(frozen=True)
class HarnessResult:
    """Execution metadata for one completed harness turn."""

    plan: HarnessTurnPlan
    provider_session_id: str | None = None


class ChatHarness:
    """Small adapter that normalizes provider execution behind a harness contract."""

    async def plan_turn(
        self,
        provider: Provider,
        provider_name: str,
        model: str | None,
        available_tools: list[ToolDescriptor] | None = None,
        prompt: str = "",
        trace: TraceRecorder | None = None,
    ) -> HarnessTurnPlan:
        return await plan_turn(
            provider=provider,
            provider_name=provider_name,
            model=model,
            prompt=prompt,
            available_tools=available_tools,
            trace=trace,
        )

    async def run_turn(
        self,
        provider: Provider,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
        available_tools: list[ToolDescriptor] | None = None,
        tool_executor: ToolExecutor | None = None,
        tool_context: ToolExecutionContext | None = None,
        trace: TraceRecorder | None = None,
        prompt_context_builder: Callable[[HarnessTurnPlan], str | None] | None = None,
    ) -> tuple[HarnessTurnPlan, AsyncIterator[ProviderEvent]]:
        """Return the normalized plan and provider event stream."""
        plan = await self.plan_turn(
            provider=provider,
            provider_name=getattr(provider, "name", "unknown"),
            model=model,
            available_tools=available_tools,
            prompt=prompt,
            trace=trace,
        )
        context_overlay = prompt_context_builder(plan) if prompt_context_builder is not None else None
        combined_system_prompt = "\n\n".join(part for part in (system_prompt, context_overlay) if part)
        effective_system_prompt = combined_system_prompt or None
        decision_record = await resolve_harness_decision_record(
            provider=provider,
            prompt=prompt,
            model=model,
            system_prompt=effective_system_prompt,
            tools=plan.tools,
            turn_id=plan.turn_id,
            decision_id=plan.decision_id,
            trace=trace,
        )
        plan = replace(plan, harness_decision=decision_record.to_public_dict())
        if plan.tool_execution_mode == "prompted" and tool_executor is not None and tool_context is not None:
            stream = run_with_prompted_tools(
                provider=provider,
                prompt=prompt,
                provider_session_id=provider_session_id,
                abort_event=abort_event,
                model=model,
                system_prompt=effective_system_prompt,
                plan=plan,
                tool_executor=tool_executor,
                tool_context=tool_context,
                trace=trace,
            )
            return plan, stream

        if (
            not plan.will_attempt_tool_loop
            or plan.tool_execution_mode != "native"
            or not hasattr(provider, "chat_completion")
            or tool_executor is None
            or tool_context is None
        ):
            stream = provider.run(
                prompt=compose_provider_prompt(provider, prompt, effective_system_prompt),
                provider_session_id=provider_session_id,
                abort_event=abort_event,
                model=model,
                system_prompt=provider_system_prompt(provider, effective_system_prompt),
            )
            return plan, stream

        stream = run_with_native_tools(
            provider=provider,  # type: ignore[arg-type]
            prompt=prompt,
            provider_session_id=provider_session_id,
            abort_event=abort_event,
            model=model,
            system_prompt=effective_system_prompt,
            plan=plan,
            tool_executor=tool_executor,
            tool_context=tool_context,
            trace=trace,
        )
        return plan, stream


__all__ = [
    "ChatHarness",
    "HarnessResult",
    "HarnessTurnPlan",
    "ModelCapabilityProfile",
]
