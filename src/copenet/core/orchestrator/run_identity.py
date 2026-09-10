"""Build persona and memory overlays under the current prompt policy."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from . import Orchestrator


from copenet.core.harness import PromptOverlay
from copenet.prompts import (
    PromptContextPolicy,
)


def _build_identity_memory_overlay(
    *,
    orchestrator: "Orchestrator",
    plan,
    query: str,
    provider: str,
    model: str | None,
    persona_id: str | None,
    persona_flavor_id: str | None,
    persona_privacy_tier: str | None,
    policy: PromptContextPolicy,
    sink: dict[str, object],
) -> PromptOverlay:
    persona_payload = (
        orchestrator._persona_service.build_prompt_context(
            provider=provider,
            model=model,
            privacy_tier=persona_privacy_tier,  # type: ignore[arg-type]
            query=query,
            include_agent_instructions=policy.include_persona_agent_instructions,
        )
        if policy.include_persona_context
        else None
    )
    memory_payload = (
        orchestrator._memory_service.build_prompt_payload(
            query=query,
            limit=3 if plan.will_attempt_tool_loop else 1,
        )
        if policy.include_relevant_memory
        else None
    )
    sink["memoryCount"] = len(memory_payload.memory_items) if memory_payload is not None else 0
    sink["memoryItemIds"] = (
        [item.id for item in memory_payload.memory_items] if memory_payload is not None else []
    )
    sink["personaActive"] = bool(persona_payload and persona_payload.prompt)
    sink["personaId"] = persona_id or (persona_payload.persona_id if persona_payload is not None else None)
    sink["personaFlavorId"] = persona_flavor_id or (
        persona_payload.flavor_id if persona_payload is not None else None
    )
    sink["personaPrivacyTier"] = persona_privacy_tier or (
        persona_payload.privacy_tier if persona_payload is not None else None
    )
    # Kept separate: persona is spliced into the base contract's `{{persona}}` slot,
    # while memory is turn context appended after it. Joining them here (the old
    # behavior) forced both to land at the end, which put voice in the prompt's
    # strongest position.
    return PromptOverlay(
        persona=(persona_payload.prompt or None) if persona_payload is not None else None,
        memory=(memory_payload.digest or None) if memory_payload is not None else None,
    )
