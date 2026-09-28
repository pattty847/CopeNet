"""Shell read-only tool handlers."""

from __future__ import annotations

import re
import shlex

from copenet.core.tools.contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

from ._shared import (
    expand_shell_argv,
    run_command,
    run_shell_command,
)
from .shell_guard import classify_guarded_command

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


def approval_required_result(command: str, context: ToolExecutionContext) -> ToolExecutionResult | None:
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


# Block kinds that Ask mode converts into an operator prompt rather than a hard
# wall. egress/barricade blocks are not in this set — those stay hard blocks.
_ASK_PROMPTABLE_DECISIONS = frozenset({"unsafe_unknown", "write_blocked"})


def _is_pre_approved(command: str, context: ToolExecutionContext) -> bool:
    """True when the operator already approved this exact command this run."""
    approved = context.ephemeral.get("approved_commands") if isinstance(context.ephemeral, dict) else None
    return isinstance(approved, (set, frozenset, list, tuple)) and command in approved


def _is_standing_approved(command: str, context: ToolExecutionContext) -> bool:
    """True when this command carries a standing operator approval.

    Either approved earlier this run (run-scoped `approved_commands`) or on the
    persisted global allowlist (Brick E). Standing-approved commands run with full
    shell in any Access mode — the operator already blessed this exact command.
    """
    if _is_pre_approved(command, context):
        return True
    store = getattr(context, "permission_store", None)
    if store is None:
        return False
    try:
        return bool(store.is_allowed(command))
    except Exception:  # noqa: BLE001 - allowlist read must never break execution
        return False


def _ask_approval_result(command: str, context: ToolExecutionContext, exc: ToolBlockedError) -> ToolExecutionResult:
    """Turn a guarded-mode block into an operator approval prompt (Ask mode).

    Carries `command` in the output so the approval-gated executor re-runs this
    exact command after approval (it keys `approved_commands` off output.command).
    """
    return ToolExecutionResult(
        tool_id="shell.exec",
        ok=False,
        summary="Shell command needs your approval (Ask mode).",
        error=f"approval required (ask mode): {exc}",
        output={
            "command": command,
            "target": command,
            "workspaceRoot": str(context.session_workspace_root),
            "scope": exc.scope or "outside_workspace",
            "accessAction": exc.access_action,
            "policyDecision": "approval_required",
            "policySummary": (
                "Ask mode: this command is outside the read-only allowlist and needs "
                "operator approval before it runs."
            ),
        },
    )


async def _run_unrestricted_shell(
    command: str,
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
    *,
    summary: str,
    policy_summary: str,
) -> ToolExecutionResult:
    """Execute a command with full shell syntax (full-access + approved Ask commands)."""
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
        "policySummary": policy_summary,
    }
    if code != 0:
        return ToolExecutionResult(
            tool_id=request.tool_id,
            ok=False,
            summary=f"Shell command failed with exit {code}.",
            error=stderr_text or stdout_text or f"command failed with exit {code}",
            output=output,
        )
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=output)


async def _run_guarded_shell(
    command: str,
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
) -> ToolExecutionResult:
    """Guarded read-only execution: classify each command before running it.

    Raises ToolBlockedError for anything outside the read-only contract. Ask mode
    catches those and converts them to operator prompts; read-only lets them raise.
    """
    # Pipes and redirection can hide write effects — always blocked in guarded mode.
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
    access = classify_guarded_command(argv, command, context)
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

    # Full Access: arbitrary shell, only high-risk patterns pause for approval.
    if context.policy.unrestricted_shell:
        approval_result = approval_required_result(command, context)
        if approval_result is not None:
            return approval_result
        return await _run_unrestricted_shell(
            command,
            request,
            context,
            summary="Ran full-access shell command.",
            policy_summary="Full-access shell command executed with the current user's permissions.",
        )

    ask_mode = bool(getattr(context.policy, "prompt_on_block", False))

    # Standing approval (Brick E): a command on the global allowlist — or approved
    # earlier this run — runs with full shell in any mode, no re-prompt. The
    # operator already blessed this exact command.
    if _is_standing_approved(command, context):
        return await _run_unrestricted_shell(
            command,
            request,
            context,
            summary="Ran operator-approved shell command.",
            policy_summary="Operator-approved shell command executed (standing allowlist).",
        )

    # Guarded read-only path. In Ask mode, a block becomes an operator prompt.
    try:
        return await _run_guarded_shell(command, request, context)
    except ToolBlockedError as exc:
        if ask_mode and exc.policy_decision in _ASK_PROMPTABLE_DECISIONS:
            return _ask_approval_result(command, context, exc)
        raise


async def _run_chain(
    command: str,
    request: ToolExecutionRequest,
    context: ToolExecutionContext,
) -> ToolExecutionResult:
    """Run a &&/; chain after classifying every segment."""
    segments = [s for s in _CHAIN_SPLIT_RE.split(command) if s.strip()]
    validated_argv: list[list[str]] = []
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
        if not seg_argv:
            raise ValueError("command is required")
        classify_guarded_command(seg_argv, command, context)
        validated_argv.append(seg_argv)

    stdout_parts: list[str] = []
    stderr_parts: list[str] = []
    final_code = 0
    for seg_argv in validated_argv:
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
