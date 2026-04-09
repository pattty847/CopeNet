"""Shell read-only tool handlers."""

from __future__ import annotations

import shlex

from copenet.core.tools.contracts import ToolBlockedError, ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

from ._shared import expand_shell_argv, run_command


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


async def shell_exec(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    if not context.policy.allow_shell:
        raise ToolBlockedError("shell execution disabled by policy")
    command = str(request.arguments.get("command") or "").strip()
    if not command:
        raise ValueError("command is required")
    argv = expand_shell_argv(shlex.split(command))
    if not argv:
        raise ValueError("command is required")
    if argv[0] not in context.policy.shell_allowlist:
        raise ToolBlockedError(f"command not allowed: {argv[0]}")
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
        output={"command": command, "stdout": stdout_text, "stderr": stderr_text},
    )


HANDLERS = {"shell.exec": shell_exec}
