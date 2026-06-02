"""Filesystem tool handlers."""

from __future__ import annotations

import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess

from copenet.core.tools.contracts import ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult

from ._shared import display_path, ensure_write_allowed, file_access_metadata, resolve_relative_path


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
        evidence_role="discovery",
        side_effect="read",
    ),
    ToolDescriptor(
        id="files.read",
        name="Read File",
        description=(
            "Read a text file inside the current workdir. "
            "Supports offset (0-based char) and limit (char count). "
            "Returns content with an English continuation hint if truncated."
        ),
        category="repo-read",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1},
            },
        },
        capabilities=["filesystem", "read"],
        evidence_role="grounding",
        side_effect="read",
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
        evidence_role="discovery",
        side_effect="read",
    ),
    ToolDescriptor(
        id="files.rg",
        name="Ripgrep Search",
        description=(
            "Search file contents under the current workdir with ripgrep (regex pattern). "
            "Supports offset/limit paging and context_lines (lines of context around each match); "
            "returns a continuation hint when matches are truncated."
        ),
        category="repo-read",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1},
                "context_lines": {"type": "integer", "minimum": 0},
            },
        },
        capabilities=["filesystem", "search", "ripgrep"],
        evidence_role="discovery",
        side_effect="read",
    ),
    ToolDescriptor(
        id="files.write",
        name="Write File",
        description=(
            "Create or overwrite a text file inside the current workdir. "
            "Pass expected_digest from a prior files.read to guard against stale overwrites."
        ),
        category="repo-write",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "expected_digest": {"type": "string"},
            },
            "required": ["path", "content"],
        },
        capabilities=["filesystem", "write"],
        evidence_role="mutation",
        side_effect="write",
    ),
    ToolDescriptor(
        id="files.edit",
        name="Edit File",
        description=(
            "Replace an exact text span in an existing file inside the current workdir. "
            "Set replace_all to change every occurrence; pass expected_digest from files.read for stale-write protection."
        ),
        category="repo-write",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "replace_all": {"type": "boolean"},
                "expected_digest": {"type": "string"},
            },
            "required": ["path", "old_text", "new_text"],
        },
        capabilities=["filesystem", "write", "edit"],
        evidence_role="mutation",
        side_effect="write",
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
    access = file_access_metadata(root, context)
    target = access["target"]
    rows = []
    for file_path in sorted(root.iterdir())[: context.policy.list_result_limit]:
        rows.append(
            {
                "path": display_path(file_path, context),
                "name": file_path.name,
                "isDir": file_path.is_dir(),
            }
        )
    summary = f"Listed {len(rows)} entries under {target if target != str(context.workdir) else '.'}."
    output = {
        "entries": rows,
        **access,
    }
    if warning_message:
        summary = f"{summary} Warning: {warning_message}"
        output["warning"] = warning_message
    return ToolExecutionResult(tool_id=request.tool_id, ok=True, summary=summary, output=output)


FILE_READ_ABSOLUTE_MAX = 500_000  # ~500KB safety guard; honors explicit limit up to here.


async def read_file(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    path = resolve_relative_path(str(request.arguments.get("path") or ""), context)
    offset = max(int(request.arguments.get("offset") or 0), 0)
    requested_limit = int(request.arguments.get("limit") or 0)
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
            f"path is a directory: {display_path(path, context)}; use files.list to inspect directories or files.search to search inside them"
        )
    if not path.is_file():
        raise RuntimeError(f"file not found: {path}")
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        full_text = handle.read()
    # Phase 0.2: honor explicit limit up to FILE_READ_ABSOLUTE_MAX. When limit
    # is omitted, default to adaptive paging using the policy's file_output_limit
    # as the page size — and emit an English continuation hint on truncation.
    if requested_limit > 0:
        effective_limit = min(requested_limit, FILE_READ_ABSOLUTE_MAX)
    else:
        effective_limit = context.policy.file_output_limit
    text = full_text[offset : offset + effective_limit]
    access = file_access_metadata(path, context)
    target = access["target"]
    digest = _content_digest(full_text)
    _remember_file_digest(context, target=target, digest=digest)
    next_offset = offset + len(text)
    truncated = next_offset < len(full_text)
    if truncated:
        kb_read = max(len(text) // 1024, 1)
        text = (
            f"{text}\n\n[Read truncated at char {next_offset} (~{kb_read}KB). "
            f"Use offset={next_offset} to continue.]"
        )
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=(
            f"Read file {target}."
            + (f" Warning: {warning_message}" if warning_message else "")
        ),
        output={
            "path": target,
            **access,
            "content": text,
            "digest": digest,
            "offset": offset,
            "limit": effective_limit,
            "totalChars": len(full_text),
            "truncated": truncated,
            **({"nextOffset": next_offset} if truncated else {}),
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
    access = file_access_metadata(root, context)
    target = access["target"]
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
                    "path": display_path(file_path, context),
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
            **access,
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
    offset = max(int(request.arguments.get("offset") or 0), 0)
    requested_limit = int(request.arguments.get("limit") or 0)
    effective_limit = requested_limit if requested_limit > 0 else context.policy.search_result_limit
    context_lines = max(int(request.arguments.get("context_lines") or 0), 0)
    root = resolve_relative_path(str(request.arguments.get("path") or "."), context)
    if not root.exists():
        raise RuntimeError(f"path not found: {root}")
    access = file_access_metadata(root, context)
    target = access["target"]
    rg_argv = ["rg", "--json", "--line-number", "--column", "--color", "never"]
    if context_lines:
        rg_argv += ["--context", str(context_lines)]
    rg_argv += [pattern, str(root)]
    try:
        completed = subprocess.run(
            rg_argv,
            cwd=context.workdir,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("ripgrep (rg) is not installed or not available on PATH") from exc

    all_hits: list[dict[str, object]] = []
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
        if path_text:
            hit_path = Path(path_text)
            resolved_hit_path = (root / hit_path).resolve() if not hit_path.is_absolute() else hit_path.resolve()
            display_hit_path = display_path(resolved_hit_path, context)
        else:
            display_hit_path = path_text
        snippet = str(lines.get("text") or "").rstrip("\n")
        column = 1
        if submatches and isinstance(submatches, list):
            first = submatches[0] if isinstance(submatches[0], dict) else {}
            column = int(first.get("start") or 0) + 1
        all_hits.append(
            {
                "path": display_hit_path,
                "line": line_number,
                "column": column,
                "text": snippet[:240],
            }
        )

    total_matches = len(all_hits)
    hits = all_hits[offset : offset + effective_limit]
    next_offset = offset + len(hits)
    truncated = next_offset < total_matches
    summary = f"Found {total_matches} matches for pattern via ripgrep; returning {len(hits)}."
    if truncated:
        summary += f" [Showing matches {offset + 1}-{next_offset}. Total found: {total_matches}. Use offset={next_offset} to continue.]"
    if warning_message:
        summary += f" Warning: {warning_message}"
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=summary,
        output={
            "matches": hits,
            "totalMatches": total_matches,
            "offset": offset,
            "limit": effective_limit,
            "truncated": truncated,
            **({"nextOffset": next_offset} if truncated else {}),
            **access,
            **({"warning": warning_message} if warning_message else {}),
        },
    )


async def write_file(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    path = resolve_relative_path(str(request.arguments.get("path") or ""), context)
    content = request.arguments.get("content")
    expected_digest = str(request.arguments.get("expected_digest") or "").strip() or None
    if not path.name:
        raise ValueError("path is required")
    if not isinstance(content, str):
        raise ValueError("content is required")
    ensure_write_allowed(path, context)
    _ensure_expected_digest(path, expected_digest=expected_digest, context=context)
    existed = path.is_file()
    before = path.read_text(encoding="utf-8", errors="replace") if existed else ""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    access = file_access_metadata(path, context)
    access["accessAction"] = "write"
    access["policySummary"] = "Write stayed inside the home workspace."
    digest = _content_digest(content)
    _remember_file_digest(context, target=access["target"], digest=digest)
    _record_edit_backup(context, target=access["target"], after_digest=digest, before=before)
    diff_fields = _unified_diff_fields(before=before, after=content, path=access["target"])
    verb = "Wrote" if existed else "Created"
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=f"{verb} file {access['target']} (+{diff_fields['linesAdded']}/-{diff_fields['linesRemoved']}).",
        output={
            "path": access["target"],
            "bytes": len(content.encode("utf-8")),
            "digest": digest,
            "created": not existed,
            **diff_fields,
            **access,
        },
    )


async def edit_file(request: ToolExecutionRequest, context: ToolExecutionContext) -> ToolExecutionResult:
    path = resolve_relative_path(str(request.arguments.get("path") or ""), context)
    old_text = request.arguments.get("old_text")
    new_text = request.arguments.get("new_text")
    replace_all = bool(request.arguments.get("replace_all"))
    expected_digest = str(request.arguments.get("expected_digest") or "").strip() or None
    if not path.name:
        raise ValueError("path is required")
    if not isinstance(old_text, str) or not old_text:
        raise ValueError("old_text is required")
    if not isinstance(new_text, str):
        raise ValueError("new_text is required")
    ensure_write_allowed(path, context)
    if not path.is_file():
        raise RuntimeError(f"file not found: {path}")
    _ensure_expected_digest(path, expected_digest=expected_digest, context=context)
    text = path.read_text(encoding="utf-8", errors="replace")
    occurrence_count = text.count(old_text)
    if occurrence_count == 0:
        raise RuntimeError(f"old_text not found in {display_path(path, context)}")
    if occurrence_count > 1 and not replace_all:
        raise RuntimeError(
            f"old_text appears {occurrence_count} times in {display_path(path, context)}; set replace_all=true or choose a more specific old_text"
        )
    next_text = text.replace(old_text, new_text) if replace_all else text.replace(old_text, new_text, 1)
    path.write_text(next_text, encoding="utf-8")
    access = file_access_metadata(path, context)
    access["accessAction"] = "write"
    access["policySummary"] = "Write stayed inside the home workspace."
    replacements = occurrence_count if replace_all else 1
    digest = _content_digest(next_text)
    _remember_file_digest(context, target=access["target"], digest=digest)
    _record_edit_backup(context, target=access["target"], after_digest=digest, before=text)
    diff_fields = _unified_diff_fields(before=text, after=next_text, path=access["target"])
    return ToolExecutionResult(
        tool_id=request.tool_id,
        ok=True,
        summary=(
            f"Edited file {access['target']} "
            f"({replacements} replacement{'s' if replacements != 1 else ''}, "
            f"+{diff_fields['linesAdded']}/-{diff_fields['linesRemoved']})."
        ),
        output={
            "path": access["target"],
            "replacements": replacements,
            "digest": digest,
            **diff_fields,
            **access,
        },
    )


HANDLERS = {
    "files.list": list_files,
    "files.read": read_file,
    "files.search": search_files,
    "files.rg": ripgrep_files,
    "files.write": write_file,
    "files.edit": edit_file,
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


def _content_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _record_edit_backup(context: ToolExecutionContext, *, target: str, after_digest: str, before: str) -> None:
    """Snapshot pre-edit content so the operator can revert from the UI diff.

    Best-effort: keyed by (session_key, path, after_digest); never fails the edit.
    """
    store = getattr(context, "edit_backup_store", None)
    session_key = getattr(context, "session_key", None)
    if store is None or not session_key:
        return
    try:
        store.record(
            session_key=session_key,
            path=target,
            after_digest=after_digest,
            before_content=before,
            run_id=getattr(context, "run_id", None),
        )
    except Exception:
        pass


# Diffs are surfaced inline in the chat (operator sees what the model changed) and
# also fed back to the model as its tool result. Keep them bounded well under the
# 4000-char artifact threshold (tool_loop.LARGE_TOOL_RESULT_CHAR_LIMIT) so they
# stay inline-renderable instead of being collapsed into an artifact preview.
DIFF_MAX_LINES = 160
DIFF_MAX_CHARS = 3200


def _unified_diff_fields(*, before: str, after: str, path: str) -> dict:
    """Build a bounded unified diff + line counts for a write/edit result.

    Field names are the contract the frontend diff renderer consumes:
      diff           unified-diff text (truncated if oversized)
      linesAdded     count of added lines (excludes the +++ header)
      linesRemoved   count of removed lines (excludes the --- header)
      diffTruncated  true when the diff was clipped for size
    """
    diff_lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    truncated = False
    if len(diff_lines) > DIFF_MAX_LINES:
        diff_lines = diff_lines[:DIFF_MAX_LINES]
        truncated = True
    diff_text = "\n".join(diff_lines)
    if len(diff_text) > DIFF_MAX_CHARS:
        diff_text = diff_text[:DIFF_MAX_CHARS].rstrip()
        truncated = True
    return {
        "diff": diff_text,
        "linesAdded": added,
        "linesRemoved": removed,
        "diffTruncated": truncated,
    }


def _remember_file_digest(context: ToolExecutionContext, *, target: str, digest: str) -> None:
    state = context.ephemeral.setdefault("file_read_state", {})
    state[target] = digest


def _ensure_expected_digest(
    path: Path,
    *,
    expected_digest: str | None,
    context: ToolExecutionContext,
) -> None:
    if not expected_digest or not path.exists() or not path.is_file():
        return
    current_text = path.read_text(encoding="utf-8", errors="replace")
    current_digest = _content_digest(current_text)
    if current_digest != expected_digest:
        display = display_path(path, context)
        raise RuntimeError(
            f"stale read detected for {display}; expected digest {expected_digest}, current digest {current_digest}"
        )
