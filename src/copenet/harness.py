"""CopeNet-native harness abstractions and one-step tool loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable

from copenet.providers import Provider, ProviderEvent
from copenet.tools import (
    ToolDescriptor,
    ToolExecutionContext,
    ToolExecutionRequest,
    ToolExecutionResult,
    build_tool_prompt_section,
    extract_tool_invocation,
)


@dataclass(frozen=True)
class ModelCapabilityProfile:
    """Normalized model/provider capability flags."""

    provider: str
    model: str | None
    chat: bool = True
    embeddings: bool = False
    tool_calls: bool = False
    streaming: bool = True
    resume: bool = False
    prompted_tool_use: bool = False


@dataclass(frozen=True)
class HarnessTurnPlan:
    """Resolved execution plan for one harness turn."""

    provider: str
    model: str | None
    capability_profile: ModelCapabilityProfile
    tools: list[ToolDescriptor] = field(default_factory=list)
    will_attempt_tool_loop: bool = False


@dataclass(frozen=True)
class HarnessResult:
    """Execution metadata for one completed harness turn."""

    plan: HarnessTurnPlan
    provider_session_id: str | None = None
    tool_result: ToolExecutionResult | None = None


ToolExecutor = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]
TraceRecorder = Callable[[str, dict[str, Any] | None], None]


class ChatHarness:
    """Small adapter that normalizes provider execution behind a harness contract."""

    async def plan_turn(
        self,
        provider: Provider,
        provider_name: str,
        model: str | None,
        available_tools: list[ToolDescriptor] | None = None,
        trace: TraceRecorder | None = None,
    ) -> HarnessTurnPlan:
        tools = available_tools or []
        provider_meta = await provider.describe()
        caps = provider_meta.get("capabilities") if isinstance(provider_meta, dict) else {}
        profile = ModelCapabilityProfile(
            provider=provider_name,
            model=model,
            chat=bool((caps or {}).get("chat", True)),
            embeddings=bool((caps or {}).get("embeddings", False)),
            tool_calls=bool((caps or {}).get("toolCalls", False)),
            streaming=bool((caps or {}).get("streaming", True)),
            resume=bool((caps or {}).get("resume", False)),
            prompted_tool_use=bool((caps or {}).get("toolCalls", False)),
        )
        plan = HarnessTurnPlan(
            provider=provider_name,
            model=model,
            capability_profile=profile,
            tools=tools,
            will_attempt_tool_loop=bool(tools and profile.prompted_tool_use),
        )
        if trace is not None:
            trace(
                "harness_planned",
                {
                    "capabilityProfile": {
                        "provider": profile.provider,
                        "model": profile.model,
                        "chat": profile.chat,
                        "embeddings": profile.embeddings,
                        "toolCalls": profile.tool_calls,
                        "streaming": profile.streaming,
                        "resume": profile.resume,
                        "promptedToolUse": profile.prompted_tool_use,
                    },
                    "willAttemptToolLoop": plan.will_attempt_tool_loop,
                    "availableToolIds": [tool.id for tool in tools],
                },
            )
        return plan

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
        plan = await self.plan_turn(
            provider=provider,
            provider_name=getattr(provider, "name", "unknown"),
            model=model,
            available_tools=available_tools,
            trace=trace,
        )
        if not plan.will_attempt_tool_loop or tool_executor is None or tool_context is None:
            stream = provider.run(
                prompt=self._compose_provider_prompt(provider, prompt, system_prompt),
                provider_session_id=provider_session_id,
                abort_event=abort_event,
                model=model,
                system_prompt=self._provider_system_prompt(provider, system_prompt),
            )
            return plan, stream
        stream = self._run_with_one_tool(
            provider=provider,
            prompt=prompt,
            provider_session_id=provider_session_id,
            abort_event=abort_event,
            model=model,
            system_prompt=system_prompt,
            plan=plan,
            tool_executor=tool_executor,
            tool_context=tool_context,
            trace=trace,
        )
        return plan, stream

    async def _run_with_one_tool(
        self,
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
        first_prompt = self._compose_tool_attempt_prompt(prompt=prompt, tools=plan.tools)
        first_system_prompt = self._compose_system_prompt(
            provider=provider,
            system_prompt=system_prompt,
            extra_instructions=build_tool_prompt_section(plan.tools),
        )
        first_events, discovered_provider_session_id = await self._collect_provider_turn(
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

        follow_up_prompt = self._compose_tool_follow_up_prompt(
            user_prompt=prompt,
            tool_result=tool_result,
        )
        second_events, _ = await self._collect_provider_turn(
            provider=provider,
            prompt=follow_up_prompt,
            provider_session_id=discovered_provider_session_id,
            abort_event=abort_event,
            model=model,
            system_prompt=self._compose_system_prompt(
                provider=provider,
                system_prompt=system_prompt,
                extra_instructions="Use the tool result to answer the user directly. Do not request another tool.",
            ),
            trace=trace,
            phase="tool-follow-up",
        )
        for event in second_events:
            yield event

    async def _collect_provider_turn(
        self,
        provider: Provider,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None,
        system_prompt: str | None,
        trace: TraceRecorder | None = None,
        phase: str = "provider",
    ) -> tuple[list[ProviderEvent], str | None]:
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
            prompt=self._compose_provider_prompt(provider, prompt, system_prompt),
            provider_session_id=provider_session_id,
            abort_event=abort_event,
            model=model,
            system_prompt=self._provider_system_prompt(provider, system_prompt),
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

    def _compose_tool_attempt_prompt(self, prompt: str, tools: list[ToolDescriptor]) -> str:
        return (
            "User request:\n"
            f"{prompt}\n\n"
            "Decide whether you need exactly one tool before answering. "
            "If needed, respond only with the JSON tool invocation."
            f"\n\n{build_tool_prompt_section(tools)}"
        )

    def _compose_tool_follow_up_prompt(
        self,
        user_prompt: str,
        tool_result: ToolExecutionResult,
    ) -> str:
        return (
            "Original user request:\n"
            f"{user_prompt}\n\n"
            "Tool result:\n"
            f"{tool_result.to_prompt_payload()}\n\n"
            "Answer the user directly using the tool result. "
            "If the tool result is insufficient, say what is still missing."
        )

    def _compose_system_prompt(
        self,
        provider: Provider,
        system_prompt: str | None,
        extra_instructions: str | None = None,
    ) -> str | None:
        parts = [part.strip() for part in (system_prompt or "", extra_instructions or "") if part and part.strip()]
        if not parts:
            return None
        return "\n\n".join(parts)

    def _provider_system_prompt(self, provider: Provider, system_prompt: str | None) -> str | None:
        if getattr(provider, "name", "") == "codex-cli":
            return None
        return system_prompt

    def _compose_provider_prompt(
        self,
        provider: Provider,
        prompt: str,
        system_prompt: str | None,
    ) -> str:
        if getattr(provider, "name", "") != "codex-cli" or not system_prompt:
            return prompt
        return (
            "System instructions:\n"
            f"{system_prompt}\n\n"
            "User request:\n"
            f"{prompt}"
        )
