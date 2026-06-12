"""Shell read-only tool handlers."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from copenet.core.tools.contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

from ._shared import (
    display_path,
    expand_shell_argv,
    policy_decision_for_scope,
    resolve_relative_path,
    run_command,
    run_shell_command,
    scope_for_path,
)

# Tokens that can hide write effects — always blocked in default mode.
_HARD_BLOCKED_TOKENS = ("|", ">")
# Pattern that splits a command on safe chaining operators.
_CHAIN_SPLIT_RE = re.compile(r"\s*(?:&&|;)\s*")


DESCRIPTORS = [
    ToolDescriptor(
        id="shell.exec",
        name="Shell Exec",
        description=(
            "Run a shell command in the current workdir. Default modes allow one read-only allowlisted command. "
            "Task mode full-access allows arbitrary user-level shell syntax except commands that require operator approval."
        ),
        category="shell-read",
        input_schema={
            "type": "object",
            "properties": {"command": {"type": "string"}},
            "required": ["command"],
            "additionalProperties": False,
        },
        safety_level="guarded",
        capabilities=["shell", "read"],
        evidence_role="verification",
        side_effect="external",
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

# Action predicates that make `find` write or execute. `find` is allowlisted as a
# read tool, but the allowlist only inspects argv[0] — so `find . -delete` and
# `find . -exec rm {} +` would pass straight through. Block them in guarded mode.
_FIND_WRITE_PREDICATES = frozenset({
    "-delete",
    "-exec",
    "-execdir",
    "-ok",
    "-okdir",
    "-fprint",
    "-fprintf",
    "-fprint0",
    "-fls",
})

# `git branch` is on the read safelist (listing branches is read-only), but these
# flags — or any positional branch-name argument — create, delete, rename, move,
# or re-point refs. Block those forms in guarded mode; plain listing still passes.
_GIT_BRANCH_WRITE_FLAGS = frozenset({
    "-d",
    "-D",
    "--delete",
    "-m",
    "-M",
    "--move",
    "-c",
    "-C",
    "--copy",
    "-f",
    "--force",
    "-u",
    "--set-upstream-to",
    "--unset-upstream",
    "--edit-description",
})


def _assert_no_write_predicates(argv: list[str], command: str, context: ToolExecutionContext) -> None:
    """Block write/exec forms of otherwise-allowlisted commands in guarded mode.

    The shell allowlist only checks argv[0], so write-capable flags on read
    binaries slip through. This is the second gate (after the allowlist) that
    keeps guarded mode actually read-only. Full-access mode never reaches here —
    it runs via the unrestricted branch above.
    """
    cmd = argv[0]
    if cmd == "find":
        for token in argv[1:]:
            base = token.split("=", 1)[0]
            if base in _FIND_WRITE_PREDICATES:
                raise ToolBlockedError(
                    f"find predicate '{base}' can write or execute and is blocked in guarded mode",
                    target=command,
                    workspace_root=str(context.session_workspace_root),
                    access_action="write",
                    policy_decision="write_blocked",
                    policy_summary="find write/exec predicates require full-access.",
                )
    elif cmd == "git" and len(argv) > 1 and argv[1] == "branch":
        for token in argv[2:]:
            base = token.split("=", 1)[0]
            if base in _GIT_BRANCH_WRITE_FLAGS or not token.startswith("-"):
                raise ToolBlockedError(
                    "git branch with a write flag or branch-name argument is blocked in guarded mode",
                    target=command,
                    workspace_root=str(context.session_workspace_root),
                    access_action="write",
                    policy_decision="write_blocked",
                    policy_summary="Only read-only `git branch` listing is allowed outside full-access.",
                )


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


def _approval_required(command: str, context: ToolExecutionContext) -> ToolExecutionResult | None:
    # Operator pre-approved this exact command via the approval flow — run it.
    approved = context.ephemeral.get("approved_commands") if isinstance(context.ephemeral, dict) else None
    if isinstance(approved, (set, frozenset, list, tuple)) and command in approved:
        return None
    normalized = " ".join(command.lower().split())
    for pattern in context.policy.shell_approval_patterns:
        if pattern.lower() in normalized:
            return ToolExecutionResult(
                tool_id="shell.exec",
                ok=False,
                summary="Shell command requires operator approval.",
                error=f"approval required for high-risk command pattern: {pattern}",
                output={
                    "command": command,
                    "target": command,
                    "workspaceRoot": str(context.session_workspace_root),
                    "scope": "outside_workspace",
                    "accessAction": "unknown",
                    "policyDecision": "approval_required",
                    "policySummary": "High-risk full-access shell command requires operator approval before execution.",
                },
            )
    return None


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
    if context.policy.unrestricted_shell:
        approval_result = _approval_required(command, context)
        if approval_result is not None:
            return approval_result
        code, stdout_text, stderr_text = await run_shell_command(
            command,
            cwd=context.workdir,
            timeout_sec=context.policy.shell_timeout_sec,
            output_limit=context.policy.shell_output_limit,
        )
        output = {
            "command": command,
            "exitCode": code,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "target": command,
            "workspaceRoot": str(context.session_workspace_root),
            "scope": "outside_workspace",
            "accessAction": "unknown",
            "policyDecision": "allowed",
            "policySummary": "Full-access shell command executed with the current user's permissions.",
        }
        if code != 0:
            return ToolExecutionResult(
                tool_id=request.tool_id,
                ok=False,
                summary=f"Shell command failed with exit {code}.",
                error=stderr_text or stdout_text or f"command failed with exit {code}",
                output=output,
            )
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=True,
            summary="Ran full-access shell command.",
            output=output,
        )
    # Pipes and redirection can hide write effects — always blocked in default mode.
    if any(t in command for t in _HARD_BLOCKED_TOKENS):
        raise ToolBlockedError(
            "shell.exec does not allow pipes or redirection in default mode",
            target=command,
            workspace_root=str(context.session_workspace_root),
            access_action="unknown",
            policy_decision="unsafe_unknown",
            policy_summary="Pipes and redirection can hide file write effects.",
        )

    has_chain = "&&" in command or ";" in command
    if has_chain:
        return await _run_chain(command, request, context)

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
    _assert_no_write_predicates(argv, command, context)

    access = _shell_access_metadata(argv, context)
    code, stdout_text, stderr_text = await run_command(
        argv,
        cwd=context.workdir,
        timeout_sec=context.policy.shell_timeout_sec,
        output_limit=context.policy.shell_output_limit,
    )
    output = {
        "command": command,
        "exitCode": code,
        "stdout": stdout_text,
        "stderr": stderr_text,
        **access,
    }
    if code != 0:
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=False,
            summary=f"Shell command failed with exit {code}: {argv[0]}",
            error=stderr_text or stdout_text or f"command failed with exit {code}",
            output=output,
        )
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Ran shell command: {argv[0]}",
        output=output,
    )


async def _run_chain(
    command: str,
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
) -> ToolExecutionResult:
    """Run a &&/; chained command where every segment is individually allowlisted."""
    segments = [s for s in _CHAIN_SPLIT_RE.split(command) if s.strip()]
    for seg in segments:
        try:
            seg_argv = expand_shell_argv(shlex.split(seg))
        except ValueError as exc:
            raise ToolBlockedError(
                f"could not parse chain segment: {exc}",
                target=command,
                workspace_root=str(context.session_workspace_root),
                access_action="unknown",
                policy_decision="unsafe_unknown",
                policy_summary="Chain segment could not be parsed.",
            ) from exc
        if not seg_argv or seg_argv[0] not in context.policy.shell_allowlist:
            blocked = seg_argv[0] if seg_argv else seg.strip()
            raise ToolBlockedError(
                f"chain blocked: '{blocked}' is not in the shell allowlist",
                target=command,
                workspace_root=str(context.session_workspace_root),
                access_action="unknown",
                policy_decision="unsafe_unknown",
                policy_summary=f"'{blocked}' is outside the shell allowlist; only allowlisted commands may be chained.",
            )
        _assert_no_write_predicates(seg_argv, command, context)

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    final_code = 0
    for seg in segments:
        seg_argv = expand_shell_argv(shlex.split(seg))
        code, stdout_text, stderr_text = await run_command(
            seg_argv,
            cwd=context.workdir,
            timeout_sec=context.policy.shell_timeout_sec,
            output_limit=context.policy.shell_output_limit,
        )
        if stdout_text:
            stdout_parts.append(stdout_text)
        if stderr_text:
            stderr_parts.append(stderr_text)
        if code != 0:
            final_code = code
            break

    combined_stdout = "\n".join(stdout_parts)
    combined_stderr = "\n".join(stderr_parts)
    output = {
        "command": command,
        "exitCode": final_code,
        "stdout": combined_stdout,
        "stderr": combined_stderr,
        "target": command,
        "workspaceRoot": str(context.session_workspace_root),
        "scope": "inside_workspace",
        "accessAction": "read",
        "policyDecision": "allowed",
        "policySummary": "Chained shell commands stayed within the allowlist.",
    }
    if final_code != 0:
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=False,
            summary=f"Chained shell command failed with exit {final_code}.",
            error=combined_stderr or combined_stdout or f"command failed with exit {final_code}",
            output=output,
        )
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Ran chained shell command ({len(segments)} segments).",
        output=output,
    )


HANDLERS = {"shell.exec": shell_exec}
