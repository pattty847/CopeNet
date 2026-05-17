"""Turn planning for the CopeNet chat harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from copenet.core.tools import ToolDescriptor
from copenet.providers import Provider

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
    tool_execution_mode: Literal["none", "native", "prompted"] = "none"


async def plan_turn(
    *,
    provider: Provider,
    provider_name: str,
    model: str | None,
    prompt: str = "",
    available_tools: list[ToolDescriptor] | None = None,
    trace: TraceRecorder | None = None,
) -> HarnessTurnPlan:
    """Build a provider-capability plan without reading or classifying the prompt."""
    del prompt
    tools = list(available_tools or [])
    provider_meta = await provider.describe()
    caps = normalize_capabilities(provider_meta if isinstance(provider_meta, dict) else {})
    if model:
        try:
            models = await provider.list_models()
        except Exception:
            models = []
        matched = next((row for row in models if row.id == model), None)
        if matched is not None and isinstance(matched.capabilities, dict):
            for key, value in matched.capabilities.items():
                caps[key] = value
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
    use_native_tools = bool(tools and profile.tool_calls)
    use_prompted_tools = bool(tools and not use_native_tools and profile.prompted_tool_use)
    plan = HarnessTurnPlan(
        provider=provider_name,
        model=model,
        capability_profile=profile,
        tools=tools,
        will_attempt_tool_loop=use_native_tools or use_prompted_tools,
        tool_execution_mode="native" if use_native_tools else "prompted" if use_prompted_tools else "none",
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
                "availableToolIds": [tool.id for tool in tools],
            },
        )
    return plan
