"""Lightweight CopeNet-native harness abstractions."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from copenet.providers import Provider, ProviderEvent


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


@dataclass(frozen=True)
class ToolSpec:
    """CopeNet-native tool declaration for future harness loops."""

    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallRequest:
    """Normalized request to execute one tool call."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HarnessTurnPlan:
    """Resolved execution plan for one harness turn."""

    provider: str
    model: str | None
    capability_profile: ModelCapabilityProfile
    tools: list[ToolSpec] = field(default_factory=list)
    will_attempt_tool_loop: bool = False


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
        available_tools: list[ToolSpec] | None = None,
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
        )
        return HarnessTurnPlan(
            provider=provider_name,
            model=model,
            capability_profile=profile,
            tools=tools,
            will_attempt_tool_loop=bool(tools and profile.tool_calls),
        )

    async def run_turn(
        self,
        provider: Provider,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
        available_tools: list[ToolSpec] | None = None,
    ) -> tuple[HarnessTurnPlan, AsyncIterator[ProviderEvent]]:
        """Return the normalized plan and provider event stream."""
        plan = await self.plan_turn(
            provider=provider,
            provider_name=getattr(provider, "name", "unknown"),
            model=model,
            available_tools=available_tools,
        )
        stream = provider.run(
            prompt=prompt,
            provider_session_id=provider_session_id,
            abort_event=abort_event,
            model=model,
            system_prompt=system_prompt,
        )
        return plan, stream
