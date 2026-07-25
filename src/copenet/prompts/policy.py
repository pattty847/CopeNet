"""Central policy for deciding which context sources a model request receives."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PromptPurpose(StrEnum):
    GENERAL_CHAT = "general_chat"
    CODE = "code"
    UTILITY = "utility"
    SPECIALIZED = "specialized"


@dataclass(frozen=True)
class PromptContextPolicy:
    purpose: PromptPurpose
    include_persona_context: bool
    include_persona_agent_instructions: bool
    include_relevant_memory: bool


_CODE_PROFILE_IDS = frozenset({"builder", "code-review", "debug", "refactor"})


def purpose_for_chat_profile(profile_id: str | None) -> PromptPurpose:
    normalized = (profile_id or "").strip().lower()
    return PromptPurpose.CODE if normalized in _CODE_PROFILE_IDS else PromptPurpose.GENERAL_CHAT


def prompt_context_policy(purpose: PromptPurpose) -> PromptContextPolicy:
    if purpose == PromptPurpose.CODE:
        return PromptContextPolicy(
            purpose=purpose,
            include_persona_context=True,
            include_persona_agent_instructions=True,
            include_relevant_memory=False,
        )
    if purpose == PromptPurpose.GENERAL_CHAT:
        return PromptContextPolicy(
            purpose=purpose,
            include_persona_context=True,
            include_persona_agent_instructions=False,
            include_relevant_memory=False,
        )
    return PromptContextPolicy(
        purpose=purpose,
        include_persona_context=False,
        include_persona_agent_instructions=False,
        include_relevant_memory=False,
    )


def prompt_context_policy_for_chat(profile_id: str | None) -> PromptContextPolicy:
    return prompt_context_policy(purpose_for_chat_profile(profile_id))
