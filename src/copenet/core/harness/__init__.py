"""CopeNet-native harness abstractions and one-step tool loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
import json
from typing import AsyncIterator, Callable

from copenet.providers import Provider, ProviderEvent
from copenet.core.tools import ToolDescriptor, ToolExecutionContext
from copenet.prompts.loader import PERSONA_PLACEHOLDER, apply_persona

from .capabilities import ModelCapabilityProfile
from .decision import resolve_harness_decision_record
from .planning import HarnessTurnPlan, TraceRecorder, plan_turn
from .tool_loop import (
    DEFAULT_RESPONSES_REASONING,
    ToolExecutor,
    collect_provider_turn,
    compose_provider_prompt,
    compose_responses_tool_instructions,
    provider_system_prompt,
    run_with_prompted_tools,
    run_with_native_tools,
    run_with_responses_tools,
)


@dataclass(frozen=True)
class HarnessResult:
    """Execution metadata for one completed harness turn."""

    plan: HarnessTurnPlan
    provider_session_id: str | None = None


@dataclass(frozen=True)
class PromptOverlay:
    """Per-turn prompt context, split by where each part belongs.

    Persona and memory used to arrive pre-joined as one appended blob. They are
    separated because they are different kinds of thing: persona is identity and
    belongs in the base contract's `{{persona}}` slot, while memory is dynamic
    context for this turn and belongs after the contract.
    """

    persona: str | None = None
    memory: str | None = None


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
        prompt_context_builder: Callable[[HarnessTurnPlan], PromptOverlay | None] | None = None,
        messages: list[dict] | None = None,
        session_id: str | None = None,
        purpose: str | None = None,
        input_token_budget: int | None = None,
    ) -> tuple[HarnessTurnPlan, AsyncIterator[ProviderEvent]]:
        """Return the normalized plan and provider event stream.

        `messages` is the Responses-API input array built from the durable
        transcript (Phase 1). Prompt-based providers consume the flattened
        `prompt`; the Phase 2 Responses path (openai-codex) consumes `messages`
        directly. `session_id` feeds prompt_cache_key on the Responses path.
        """
        plan = await self.plan_turn(
            provider=provider,
            provider_name=getattr(provider, "name", "unknown"),
            model=model,
            available_tools=available_tools,
            prompt=prompt,
            trace=trace,
        )
        overlay = prompt_context_builder(plan) if prompt_context_builder is not None else None
        # Persona is spliced into the contract's slot rather than appended; memory
        # follows the contract as turn context. apply_persona falls back to appending
        # when there is no slot, so a request-supplied system_prompt still gets voice.
        personalized_prompt = apply_persona(system_prompt, overlay.persona if overlay is not None else None)
        context_overlay = overlay.memory if overlay is not None else None
        combined_system_prompt = "\n\n".join(part for part in (personalized_prompt, context_overlay) if part)
        effective_system_prompt = combined_system_prompt or None
        if trace is not None:
            trace(
                "prompt_context_assembled",
                {
                    "purpose": purpose,
                    "baseSystemPromptChars": len(system_prompt or ""),
                    # personaChars is spliced INTO the base prompt, so it is not part
                    # of contextOverlayChars — which now counts memory only. Without
                    # this field a persona-active run traces as contextOverlayChars: 0
                    # and reads as "no persona", which is how the splice would hide.
                    "personaChars": len(overlay.persona or "") if overlay is not None else 0,
                    "personaSpliced": bool(
                        overlay is not None
                        and overlay.persona
                        and system_prompt
                        and PERSONA_PLACEHOLDER in system_prompt
                    ),
                    "contextOverlayChars": len(context_overlay or ""),
                    "combinedSystemPromptChars": len(effective_system_prompt or ""),
                    "messageItemCount": len(messages or []),
                    "messagePayloadChars": len(json.dumps(messages or [], ensure_ascii=False)),
                    "toolCount": len(plan.tools),
                    "toolSchemaChars": sum(
                        len(json.dumps(tool.to_public_dict(), ensure_ascii=False))
                        for tool in plan.tools
                    ),
                },
            )
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
        if (
            plan.tool_execution_mode == "responses"
            and tool_executor is not None
            and tool_context is not None
            and hasattr(provider, "stream_responses")
        ):
            stream = run_with_responses_tools(
                provider=provider,  # type: ignore[arg-type]
                messages=list(messages or []),
                abort_event=abort_event,
                model=model,
                instructions=compose_responses_tool_instructions(
                    system_prompt=effective_system_prompt,
                    workdir=str(getattr(tool_context, "workdir", "") or "") or None,
                    tools=plan.tools,
                ),
                plan=plan,
                tool_executor=tool_executor,
                tool_context=tool_context,
                session_id=session_id or provider_session_id,
                reasoning=DEFAULT_RESPONSES_REASONING,
                input_token_budget=input_token_budget,
                trace=trace,
            )
            return plan, stream

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
