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
    # Ask mode: instead of silently blocking a command outside the read-only
    # allowlist, return `approval_required` so the operator is prompted. On approve
    # the command re-runs with full shell (via the approved_commands ephemeral set).
    prompt_on_block: bool = False
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


# Full Access (write + unrestricted shell) is only granted to frontier providers we
# trust with that power. A local/other model that requests full-access is downgraded to
# the read-only base policy. provider=None (e.g. internal callers/tests) is not gated.
FULL_ACCESS_PROVIDERS: frozenset[str] = frozenset({"claude-cli", "openai-codex"})


def policy_for_task_mode(task_prompt_id: str | None, provider: str | None = None) -> ToolPolicy:
    """Return the effective tool policy for one access level (Full Access provider-gated).

    Access levels ride on `task_prompt_id` for backwards-compat:
      - `full-access` → writes + unrestricted shell (gated to frontier providers)
      - `ask`         → read-only allowlist, but prompts the operator before running
                        anything outside it (ungated — approval is the gate)
      - anything else → read-only (the default)
    """
    normalized = (task_prompt_id or "none").strip().lower() or "none"
    base = {"repo-read", "shell-read", "context", "artifact", "web"}
    full_access_allowed = provider is None or provider.strip().lower() in FULL_ACCESS_PROVIDERS
    if normalized == "full-access" and full_access_allowed:
        return ToolPolicy(
            allowed_categories={*base, "repo-write"},
            unrestricted_shell=True,
            shell_timeout_sec=120.0,
            shell_output_limit=30000,  # match Claude Code's Bash-output default
        )
    if normalized == "ask":
        # Same read-only category set as default, but a blocked command becomes an
        # operator prompt instead of a hard wall. Approved commands run with full
        # shell, so use the elevated timeout/output ceiling like full-access.
        return ToolPolicy(
            allowed_categories=base,
            prompt_on_block=True,
            shell_timeout_sec=120.0,
            shell_output_limit=30000,
        )
    return ToolPolicy(allowed_categories=base)
