"""Prompt profiles and task overlays for CopeNet."""

from copenet.prompts.loader import (
    compose_prompt,
    get_profile_text,
    get_task_mode_text,
    list_profiles,
    list_task_modes,
)
from copenet.prompts.policy import (
    PromptContextPolicy,
    PromptPurpose,
    prompt_context_policy,
    prompt_context_policy_for_chat,
    purpose_for_chat_profile,
)

__all__ = [
    "PromptContextPolicy",
    "PromptPurpose",
    "compose_prompt",
    "get_profile_text",
    "get_task_mode_text",
    "list_profiles",
    "list_task_modes",
    "prompt_context_policy",
    "prompt_context_policy_for_chat",
    "purpose_for_chat_profile",
]
