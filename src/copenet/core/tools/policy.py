"""Tool policy definitions."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import ToolCategory


@dataclass(frozen=True)
class ToolPolicy:
    """Safety policy for the v1 tool runtime."""

    allowed_categories: set[ToolCategory] = field(
        default_factory=lambda: {"repo-read", "shell-read", "context", "artifact", "web"}
    )
    allow_shell: bool = True
    unrestricted_shell: bool = False
    # Read-only commands allowed in non-full-access modes. Write/exec forms (e.g.
    # `find -delete`) are still caught by the secondary gate in handlers/shell.py.
    shell_allowlist: tuple[str, ...] = (
        "git", "rg", "ls", "pwd", "find", "grep", "head",
        "cat", "tail", "wc", "tree", "file", "which", "diff",
    )
    shell_approval_patterns: tuple[str, ...] = (
        "rm -rf /",
        "rm -rf /*",
        "mkfs",
        "dd if=",
        "dd of=/dev/",
        ":(){",
        "shutdown",
        "reboot",
        "poweroff",
        "systemctl",
        "crontab",
        "sudo",
        "git reset",
        "git clean",
        "git checkout",
        "curl ",
        "wget ",
    )
    shell_timeout_sec: float = 5.0
    # Per-tool output caps. Sized to fill (and stay under) the harness's
    # model-facing budget (tool_loop._DEFAULT_MODEL_FACING_RESULT_CHARS, 30K,
    # matching Claude Code's Bash-output default) so a single read/command
    # returns a substantial chunk instead of a tiny slice.
    shell_output_limit: int = 16000
    file_output_limit: int = 24000
    search_result_limit: int = 80
    list_result_limit: int = 200
    transcript_limit: int = 8
    guidance_char_limit: int = 6000


def policy_for_task_mode(task_prompt_id: str | None) -> ToolPolicy:
    """Return the effective tool policy for one task mode."""
    normalized = (task_prompt_id or "none").strip().lower() or "none"
    base = {"repo-read", "shell-read", "context", "artifact", "web"}
    if normalized == "full-access":
        return ToolPolicy(
            allowed_categories={*base, "repo-write"},
            unrestricted_shell=True,
            shell_timeout_sec=120.0,
            shell_output_limit=30000,  # match Claude Code's Bash-output default
        )
    return ToolPolicy(allowed_categories=base)
