"""Shell read-only tool handlers."""

from __future__ import annotations

import shlex
from pathlib import Path

from copenet.core.tools.contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

from ._shared import display_path, expand_shell_argv, policy_decision_for_scope, resolve_relative_path, run_command, scope_for_path


DESCRIPTORS = [
    ToolDescriptor(
        id="shell.exec",
        name="Shell Exec",
        description="Run an allowlisted read-only shell command in the current workdir.",
        category="shell-read",
        input_schema={"type": "object", "properties": {"command": {"type": "string"}}},
        safety_level="guarded",
        capabilities=["shell", "read"],
    )
]

_SAFE_GIT_SUBCOMMANDS = {
    "status",
    "diff",
    "show",
    "log",
    "rev-parse",
    "branch",
    "ls-files",
    "grep",
}
_WRITE_LIKE_GIT_SUBCOMMANDS = {
    "add",
    "apply",
    "checkout",
    "cherry-pick",
    "clean",
    "commit",
    "merge",
    "mv",
    "pull",
    "push",
    "rebase",
    "reset",
    "restore",
    "revert",
    "rm",
    "stash",
    "switch",
    "tag",
}


def _path_candidate(token: str) -> bool:
    if not token or token.startswith("-"):
        return False
    if token in {".", ".."}:
        return True
    return "/" in token or token.startswith("~")


def _shell_access_metadata(argv: list[str], context: ToolExecutionContext) -> dict[str, str | None]:
    command = " ".join(argv)
    default = {
        "target": command,
        "workspaceRoot": str(context.session_workspace_root),
        "scope": None,
        "accessAction": "read",
        "policyDecision": "allowed",
        "policySummary": "Shell command stayed within the home workspace.",
    }
    cmd = argv[0]

    if cmd == "pwd":
        default["target"] = display_path(context.workdir, context)
        default["scope"] = "inside_workspace"
        return default

    if cmd == "git":
        subcommand = argv[1] if len(argv) > 1 else "status"
        if subcommand in _WRITE_LIKE_GIT_SUBCOMMANDS:
            raise ToolBlockedError(
                f"git {subcommand} may write to the repository and is blocked in shell.exec v1",
                target=command,
                workspace_root=str(context.session_workspace_root),
                access_action="write",
                policy_decision="write_blocked",
                policy_summary="Shell write blocked outside dedicated patch/apply flows.",
            )
        if subcommand not in _SAFE_GIT_SUBCOMMANDS:
            raise ToolBlockedError(
                f"git {subcommand} is not classified as safely read-only for shell.exec v1",
                target=command,
                workspace_root=str(context.session_workspace_root),
                access_action="unknown",
                policy_decision="unsafe_unknown",
                policy_summary="Shell effect is not confidently read-only.",
            )
        default["target"] = display_path(context.workdir, context)
        default["scope"] = "inside_workspace"
        return default

    path_tokens = [token for token in argv[1:] if _path_candidate(token)]
    if not path_tokens:
        default["target"] = command
        default["scope"] = "inside_workspace"
        return default

    resolved = resolve_relative_path(path_tokens[-1], context)
    scope = scope_for_path(resolved, context)
    default["target"] = display_path(resolved, context)
    default["scope"] = scope
    default["policyDecision"] = policy_decision_for_scope(scope)
    default["policySummary"] = (
        "Shell read roamed outside the home workspace."
        if scope == "outside_workspace"
        else "Shell command stayed within the home workspace."
    )
    return default


async def shell_exec(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    if not context.policy.allow_shell:
        raise ToolBlockedError(
            "shell execution disabled by policy",
            workspace_root=str(context.session_workspace_root),
            access_action="unknown",
            policy_decision="unsafe_unknown",
        )
    command = str(request.arguments.get("command") or "").strip()
    if not command:
        raise ValueError("command is required")
    if any(token in command for token in ("|", "&&", "||", ";", ">")):
        raise ToolBlockedError(
            "shell.exec accepts one allowlisted command only; do not use pipes, chaining, or redirection",
            target=command,
            workspace_root=str(context.session_workspace_root),
            access_action="unknown",
            policy_decision="unsafe_unknown",
            policy_summary="Shell syntax can hide file effects, so this form is blocked.",
        )
    argv = expand_shell_argv(shlex.split(command))
    if not argv:
        raise ValueError("command is required")
    if argv[0] not in context.policy.shell_allowlist:
        raise ToolBlockedError(
            f"command not allowed: {argv[0]}",
            target=command,
            workspace_root=str(context.session_workspace_root),
            access_action="unknown",
            policy_decision="unsafe_unknown",
            policy_summary="Command is outside the shell allowlist.",
        )

    access = _shell_access_metadata(argv, context)
    code, stdout_text, stderr_text = await run_command(
        argv,
        cwd=context.workdir,
        timeout_sec=context.policy.shell_timeout_sec,
        output_limit=context.policy.shell_output_limit,
    )
    if code != 0:
        raise RuntimeError(stderr_text or stdout_text or f"command failed with exit {code}")
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Ran shell command: {argv[0]}",
        output={"command": command, "stdout": stdout_text, "stderr": stderr_text, **access},
    )


HANDLERS = {"shell.exec": shell_exec}
