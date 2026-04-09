"""Filesystem tool handlers."""

from __future__ import annotations

import re

from copenet.core.tools.contracts import ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

from ._shared import resolve_relative_path


DESCRIPTORS = [
    ToolDescriptor(
        id="files.list",
        name="List Files",
        description="List files or directories under the current workdir.",
        category="repo-read",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        capabilities=["filesystem", "read"],
    ),
    ToolDescriptor(
        id="files.read",
        name="Read File",
        description="Read a text file inside the current workdir.",
        category="repo-read",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        capabilities=["filesystem", "read"],
    ),
    ToolDescriptor(
        id="files.search",
        name="Search Files",
        description="Search file contents under the current workdir using a regex pattern.",
        category="repo-read",
        input_schema={"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}},
        capabilities=["filesystem", "search"],
    ),
]


async def list_files(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    root = resolve_relative_path(str(request.arguments.get("path") or "."), context)
    if not root.exists():
        raise RuntimeError(f"path not found: {root}")
    rows = []
    for file_path in sorted(root.iterdir())[: context.policy.list_result_limit]:
        rows.append(
            {
                "path": str(file_path.relative_to(context.workdir)),
                "name": file_path.name,
                "isDir": file_path.is_dir(),
            }
        )
    summary = f"Listed {len(rows)} entries under {root.relative_to(context.workdir) if root != context.workdir else '.'}."
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output={"entries": rows})


async def read_file(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    path = resolve_relative_path(str(request.arguments.get("path") or ""), context)
    if not path.is_file():
        raise RuntimeError(f"file not found: {path}")
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        text = handle.read(context.policy.file_output_limit)
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Read file {path.relative_to(context.workdir)}.",
        output={"path": str(path.relative_to(context.workdir)), "content": text},
    )


async def search_files(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    pattern = str(request.arguments.get("pattern") or "").strip()
    if not pattern:
        raise ValueError("pattern is required")
    root = resolve_relative_path(str(request.arguments.get("path") or "."), context)
    regex = re.compile(pattern, re.MULTILINE)
    hits = []
    for file_path in root.rglob("*"):
        if len(hits) >= context.policy.search_result_limit:
            break
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = text.splitlines()
        for match in regex.finditer(text):
            line_no = text.count("\n", 0, match.start()) + 1
            line = lines[line_no - 1] if lines else ""
            hits.append(
                {
                    "path": str(file_path.relative_to(context.workdir)),
                    "line": line_no,
                    "text": line[:240],
                }
            )
            if len(hits) >= context.policy.search_result_limit:
                break
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"Found {len(hits)} matches for pattern.",
        output={"matches": hits},
    )


HANDLERS = {
    "files.list": list_files,
    "files.read": read_file,
    "files.search": search_files,
}
