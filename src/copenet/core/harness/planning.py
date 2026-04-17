"""Turn planning for the CopeNet chat harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from copenet.providers import Provider
from copenet.core.tools import ToolDescriptor

from .capabilities import ModelCapabilityProfile, normalize_capabilities


TraceRecorder = Callable[[str, dict[str, Any] | None], None]


@dataclass(frozen=True)
class HarnessTurnPlan:
    """Resolved execution plan for one harness turn."""

    provider: str
    model: str | None
    capability_profile: ModelCapabilityProfile
    tools: list[ToolDescriptor] = field(default_factory=list)
    will_attempt_tool_loop: bool = False
    tool_execution_mode: Literal["none", "single", "batch"] = "none"
    batch_read_allowed: bool = False


async def plan_turn(
    *,
    provider: Provider,
    provider_name: str,
    model: str | None,
    available_tools: list[ToolDescriptor] | None = None,
    trace: TraceRecorder | None = None,
) -> HarnessTurnPlan:
    """Build a normalized turn plan from provider metadata and available tools."""
    tools = available_tools or []
    provider_meta = await provider.describe()
    caps = normalize_capabilities(provider_meta if isinstance(provider_meta, dict) else {})
    profile = ModelCapabilityProfile(
        provider=provider_name,
        model=model,
        chat=caps.get("chat", True),
        embeddings=caps.get("embeddings", False),
        tool_calls=caps.get("toolCalls", False),
        streaming=caps.get("streaming", True),
        resume=caps.get("resume", False),
        prompted_tool_use=caps.get("promptedToolUse", caps.get("toolCalls", False)),
    )
    plan = HarnessTurnPlan(
        provider=provider_name,
        model=model,
        capability_profile=profile,
        tools=tools,
        will_attempt_tool_loop=bool(tools and profile.prompted_tool_use),
        tool_execution_mode="batch" if bool(tools and profile.prompted_tool_use) else "none",
        batch_read_allowed=bool(tools and profile.prompted_tool_use),
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
                "toolExecutionMode": plan.tool_execution_mode,
                "batchReadAllowed": plan.batch_read_allowed,
                "availableToolIds": [tool.id for tool in tools],
            },
        )
    return plan
