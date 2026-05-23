"""Turn planning for the CopeNet chat harness."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from copenet.core.tools import ToolDescriptor
from copenet.providers import Provider

from .capabilities import ModelCapabilityProfile, normalize_capabilities
from .decision import new_decision_id, new_turn_id


TraceRecorder = Callable[[str, dict[str, Any] | None], None]


@dataclass(frozen=True)
class HarnessTurnPlan:
    """Resolved execution plan for one harness turn."""

    provider: str
    model: str | None
    capability_profile: ModelCapabilityProfile
    tools: list[ToolDescriptor] = field(default_factory=list)
    will_attempt_tool_loop: bool = False
    tool_execution_mode: Literal["none", "native", "prompted", "responses"] = "none"
    turn_id: str = field(default_factory=new_turn_id)
    decision_id: str = field(default_factory=new_decision_id)
    harness_decision: dict[str, Any] = field(default_factory=dict)


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
        responses_api=caps.get("responsesApi", False),
    )
    # Phase 2 routing: prefer the native Responses-API loop when the provider
    # declares it. Otherwise fall back to the legacy native (Chat Completions)
    # path, then the prompted path (LM Studio / Ollama), then none.
    use_responses_tools = bool(tools and profile.responses_api)
    use_native_tools = bool(tools and not use_responses_tools and profile.tool_calls)
    use_prompted_tools = bool(
        tools and not use_responses_tools and not use_native_tools and profile.prompted_tool_use
    )
    if use_responses_tools:
        tool_execution_mode = "responses"
    elif use_native_tools:
        tool_execution_mode = "native"
    elif use_prompted_tools:
        tool_execution_mode = "prompted"
    else:
        tool_execution_mode = "none"
    plan = HarnessTurnPlan(
        provider=provider_name,
        model=model,
        capability_profile=profile,
        tools=tools,
        will_attempt_tool_loop=use_responses_tools or use_native_tools or use_prompted_tools,
        tool_execution_mode=tool_execution_mode,
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
                "turnId": plan.turn_id,
                "decisionId": plan.decision_id,
            },
        )
    return plan
