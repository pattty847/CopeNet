"""Tool policy definitions."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import ToolCategory


@dataclass(frozen=True)
class ToolPolicy:
    """Safety policy for the v1 tool runtime."""

    allowed_categories: set[ToolCategory] = field(
        default_factory=lambda: {"repo-read", "shell-read", "context", "artifact"}
    )
    allow_shell: bool = True
    shell_allowlist: tuple[str, ...] = ("git", "rg", "ls", "pwd", "find")
    shell_timeout_sec: float = 5.0
    shell_output_limit: int = 8000
    file_output_limit: int = 12000
    search_result_limit: int = 80
    list_result_limit: int = 200
    transcript_limit: int = 8
    guidance_char_limit: int = 6000


def policy_for_task_mode(task_prompt_id: str | None) -> ToolPolicy:
    """Return the effective tool policy for one task mode."""
    normalized = (task_prompt_id or "none").strip().lower() or "none"
    base = {"repo-read", "shell-read", "context", "artifact"}
    if normalized == "full-access":
        return ToolPolicy(allowed_categories={*base, "repo-write"})
    return ToolPolicy(allowed_categories=base)
