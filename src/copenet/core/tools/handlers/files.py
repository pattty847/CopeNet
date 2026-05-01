"""Filesystem tool handlers."""

from __future__ import annotations

import json
import re
import subprocess

from copenet.core.tools.contracts import ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

from ._shared import resolve_relative_path


DESCRIPTORS = [
    ToolDescriptor(
        id="files.list",
        name="List Files",
        description=(
            "List files or directories under the current workdir. "
            "Use this for reconnaissance only. A directory listing usually is not enough evidence for "
            "architecture, bug, or patch answers; follow it with files.read for direct grounding or "
            "files.search for broader discovery."
        ),
        category="repo-read",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        capabilities=["filesystem", "read"],
    ),
    ToolDescriptor(
        id="files.read",
        name="Read File",
        description=(
            "Read a text file inside the current workdir. This is the primary grounding tool for "
            "repo/code claims. Use it when you need direct evidence from a specific file."
        ),
        category="repo-read",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        capabilities=["filesystem", "read"],
    ),
    ToolDescriptor(
        id="files.search",
        name="Search Files",
        description=(
            "Search file contents under the current workdir using a regex pattern. "
            "Use this for directional discovery to find relevant files, symbols, or text, then follow "
            "up with files.read on the most relevant files."
        ),
        category="repo-read",
        input_schema={"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}},
        capabilities=["filesystem", "search"],
    ),
    ToolDescriptor(
        id="files.rg",
        name="Ripgrep Search",
        description=(
            "Search file contents under the current workdir with ripgrep. "
            "Prefer this for repository discovery before choosing files.read when the exact path is not already known."
        ),
        category="repo-read",
        input_schema={"type": "object", "properties": {"pattern": {"type": "string"}, "path": {"type": "string"}}},
        capabilities=["filesystem", "search", "ripgrep"],
    ),
]


async def list_files(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    root = resolve_relative_path(str(request.arguments.get("path") or "."), context)
    warning_message, blocked_result = _repeat_response(
        context,
        tool_id=request.tool_id,
        on_warning=(
            "Repeated identical files.list calls are low value. Use files.read for direct evidence or "
            "files.search for broader discovery."
        ),
        on_block=(
            "Blocked repeated identical files.list call. Stop repeating the same directory listing and use "
            "existing information to choose files.read or files.search."
        ),
    )
    if blocked_result is not None:
        return blocked_result
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
    output = {"entries": rows}
    if warning_message:
        summary = f"{summary} Warning: {warning_message}"
        output["warning"] = warning_message
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=output)


async def read_file(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    path = resolve_relative_path(str(request.arguments.get("path") or ""), context)
    warning_message, blocked_result = _repeat_response(
        context,
        tool_id=request.tool_id,
        on_warning=(
            "You have read the same file repeatedly. Use the information you already have unless the file changed "
            "or you need a different file."
        ),
        on_block=(
            "Blocked repeated identical files.read call. Stop re-reading the same file and use the information "
            "already gathered or inspect a different file."
        ),
    )
    if blocked_result is not None:
        return blocked_result
    if path.exists() and path.is_dir():
        raise RuntimeError(
            f"path is a directory: {path.relative_to(context.workdir)}; use files.list to inspect directories or files.search to search inside them"
        )
    if not path.is_file():
        raise RuntimeError(f"file not found: {path}")
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        text = handle.read(context.policy.file_output_limit)
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=(
            f"Read file {path.relative_to(context.workdir)}."
            + (f" Warning: {warning_message}" if warning_message else "")
        ),
        output={
            "path": str(path.relative_to(context.workdir)),
            "content": text,
            **({"warning": warning_message} if warning_message else {}),
        },
    )


async def search_files(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    pattern = str(request.arguments.get("pattern") or "").strip()
    warning_message, blocked_result = _repeat_response(
        context,
        tool_id=request.tool_id,
        on_warning=(
            "You have repeated the same files.search call several times. Use the current matches to choose a file "
            "for files.read or change the search."
        ),
        on_block=(
            "Blocked repeated identical files.search call. Stop repeating the same search and either read one of the "
            "matches or change the pattern/path."
        ),
    )
    if blocked_result is not None:
        return blocked_result
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
        summary=(
            f"Found {len(hits)} matches for pattern."
            + (f" Warning: {warning_message}" if warning_message else "")
        ),
        output={
            "matches": hits,
            **({"warning": warning_message} if warning_message else {}),
        },
    )


async def ripgrep_files(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    pattern = str(request.arguments.get("pattern") or "").strip()
    warning_message, blocked_result = _repeat_response(
        context,
        tool_id=request.tool_id,
        on_warning=(
            "You have repeated the same files.rg call several times. Use the current matches to choose a file "
            "for files.read or change the search."
        ),
        on_block=(
            "Blocked repeated identical files.rg call. Stop repeating the same search and either read one of the "
            "matches or change the pattern/path."
        ),
    )
    if blocked_result is not None:
        return blocked_result
    if not pattern:
        raise ValueError("pattern is required")
    root = resolve_relative_path(str(request.arguments.get("path") or "."), context)
    if not root.exists():
        raise RuntimeError(f"path not found: {root}")
    try:
        completed = subprocess.run(
            [
                "rg",
                "--json",
                "--line-number",
                "--column",
                "--color",
                "never",
                pattern,
                str(root.relative_to(context.workdir) if root != context.workdir else "."),
            ],
            cwd=context.workdir,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ripgrep (rg) is not installed or not available on PATH") from exc

    hits: list[dict[str, object]] = []
    stderr = completed.stderr.strip()
    if completed.returncode not in (0, 1):
        message = stderr or f"ripgrep exited with status {completed.returncode}"
        raise RuntimeError(message)

    for raw_line in completed.stdout.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            parsed = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if parsed.get("type") != "match":
            continue
        data = parsed.get("data") or {}
        path_info = data.get("path") or {}
        submatches = data.get("submatches") or []
        lines = data.get("lines") or {}
        line_number = int(data.get("line_number") or 0)
        path_text = str(path_info.get("text") or "")
        snippet = str(lines.get("text") or "").rstrip("\n")
        column = 1
        if submatches and isinstance(submatches, list):
            first = submatches[0] if isinstance(submatches[0], dict) else {}
            column = int(first.get("start") or 0) + 1
        hits.append(
            {
                "path": path_text,
                "line": line_number,
                "column": column,
                "text": snippet[:240],
            }
        )
        if len(hits) >= context.policy.search_result_limit:
            break

    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=(
            f"Found {len(hits)} matches for pattern via ripgrep."
            + (f" Warning: {warning_message}" if warning_message else "")
        ),
        output={
            "matches": hits,
            **({"warning": warning_message} if warning_message else {}),
        },
    )


HANDLERS = {
    "files.list": list_files,
    "files.read": read_file,
    "files.search": search_files,
    "files.rg": ripgrep_files,
}


def _repeat_response(
    context: ToolExecutionContext,
    *,
    tool_id: str,
    on_warning: str,
    on_block: str,
) -> tuple[str | None, ToolExecutionResult | None]:
    repetition = dict(context.ephemeral.get("tool_repetition_state", {}).get("current") or {})
    if repetition.get("toolId") != tool_id:
        return None, None
    count = int(repetition.get("count") or 0)
    if count >= 4:
        return None, ToolExecutionResult(
            tool_id=tool_id,
            ok=False,
            summary=f"Blocked repeated identical tool call: {tool_id}.",
            error=on_block,
            output={"warning": on_block, "repeatCount": count},
        )
    if count >= 3:
        return on_warning, None
    return None, None
