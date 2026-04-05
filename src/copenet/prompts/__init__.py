"""Prompt profiles and task overlays for CopeNet."""

from copenet.prompts.loader import (
    compose_prompt,
    get_preset_text,
    get_profile_text,
    get_task_mode_text,
    list_presets,
    list_profiles,
    list_task_modes,
)

__all__ = [
    "compose_prompt",
    "get_preset_text",
    "get_profile_text",
    "get_task_mode_text",
    "list_presets",
    "list_profiles",
    "list_task_modes",
]
