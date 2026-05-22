"""Git read-only tool handlers."""

from __future__ import annotations

from copenet.core.tools.contracts import ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

from ._shared import display_path, file_access_metadata, run_command


DESCRIPTORS = [
    ToolDescriptor(
        id="git.status",
        name="Git Status",
        description="Inspect git status in the current workdir.",
        category="repo-read",
        input_schema={"type": "object", "properties": {}},
        capabilities=["git", "read"],
        evidence_role="discovery",
        side_effect="read",
    ),
    ToolDescriptor(
        id="git.diff",
        name="Git Diff",
        description="Inspect git diff in the current workdir.",
        category="repo-read",
        input_schema={"type": "object", "properties": {"target": {"type": "string"}}},
        capabilities=["git", "read"],
        evidence_role="grounding",
        side_effect="read",
    ),
]


async def git_status(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    code, stdout_text, stderr_text = await run_command(
        ["git", "status", "--short", "--branch"],
        cwd=context.workdir,
        timeout_sec=context.policy.shell_timeout_sec,
        output_limit=context.policy.file_output_limit,
    )
    if code != 0:
        raise RuntimeError(stderr_text or stdout_text or "git status failed")
    access = file_access_metadata(context.workdir, context)
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary="Read git status.",
        output={"statusText": stdout_text, **access},
    )


async def git_diff(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    target = str(request.arguments.get("target") or "").strip()
    argv = ["git", "diff", "--stat", "--patch", "--minimal"]
    access = file_access_metadata(context.workdir, context)
    if target:
        argv.append(target)
        access["target"] = target
    code, stdout_text, stderr_text = await run_command(
        argv,
        cwd=context.workdir,
        timeout_sec=context.policy.shell_timeout_sec,
        output_limit=context.policy.file_output_limit,
    )
    if code != 0:
        raise RuntimeError(stderr_text or stdout_text or "git diff failed")
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary="Read git diff.",
        output={"diffText": stdout_text, **access},
    )


HANDLERS = {"git.status": git_status, "git.diff": git_diff}
