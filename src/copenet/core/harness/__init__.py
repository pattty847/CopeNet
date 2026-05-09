"""CopeNet-native harness abstractions and one-step tool loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import AsyncIterator

from copenet.providers import Provider, ProviderEvent
from copenet.core.tools import ToolDescriptor, ToolExecutionContext

from .capabilities import ModelCapabilityProfile
from .planning import HarnessTurnPlan, TraceRecorder, plan_turn
from .final_gate import FinalGateDecision, TaskContract, final_gate_evaluate
from .tool_loop import (
    ToolExecutor,
    collect_provider_turn,
    compose_interaction_system_prompt,
    compose_provider_prompt,
    provider_system_prompt,
    run_with_native_tools,
    run_with_one_tool,
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
    ) -> tuple[HarnessTurnPlan, AsyncIterator[ProviderEvent]]:
        """Return the normalized plan and provider event stream."""
        effective_tools = available_tools
        if available_tools is not None and tool_context is not None:
            effective_tools = [
                tool for tool in available_tools if tool.category in tool_context.policy.allowed_categories
            ]
        plan = await self.plan_turn(
            provider=provider,
            provider_name=getattr(provider, "name", "unknown"),
            model=model,
            available_tools=effective_tools,
            prompt=prompt,
            trace=trace,
        )
        effective_system_prompt = compose_interaction_system_prompt(
            provider=provider,
            system_prompt=system_prompt,
            plan=plan,
        )
        if not plan.will_attempt_tool_loop or tool_executor is None or tool_context is None:
            stream = provider.run(
                prompt=compose_provider_prompt(provider, prompt, effective_system_prompt),
                provider_session_id=provider_session_id,
                abort_event=abort_event,
                model=model,
                system_prompt=provider_system_prompt(provider, effective_system_prompt),
            )
            return plan, stream

        if plan.tool_execution_mode == "native" and hasattr(provider, "chat_completion"):
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
        else:
            stream = run_with_one_tool(
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


__all__ = [
    "ChatHarness",
    "HarnessResult",
    "FinalGateDecision",
    "HarnessTurnPlan",
    "ModelCapabilityProfile",
    "TaskContract",
    "final_gate_evaluate",
]
