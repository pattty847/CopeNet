"""Tool inspector previews and effect projections."""
from __future__ import annotations
import json
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .contracts import ToolExecutionResult, ToolDescriptor, ToolEvidenceRole, ToolEffectKind

# Inline inspector budget for a tool result that has no hand-written preview
# branch below. Kept at the harness spill threshold
# (tool_result_materialization.LARGE_TOOL_RESULT_CHAR_LIMIT, 4000) on purpose:
# anything larger is already persisted whole as a `tool_output` artifact, so
# pairing the two means every tool result is recoverable by one route or the
# other with no gap in between. Raising the spill threshold without raising this
# reopens that gap.
INSPECTOR_INLINE_BODY_CHARS = 4000


def _generic_preview(body: Any) -> dict[str, Any]:
    """Structural fallback so a tool with no bespoke branch is still inspectable.

    Every branch in `_preview_payload` is a hand-written lossy projection, which
    means a tool nobody wrote a branch for used to render as an empty row in the
    Inspect drawer — indistinguishable from a tool that returned nothing. This
    reports the real body plus an honest character count instead.
    """
    if isinstance(body, str):
        serialized = body
    else:
        serialized = json.dumps(body, ensure_ascii=False, indent=2, default=str)
    full_chars = len(serialized)
    if full_chars <= INSPECTOR_INLINE_BODY_CHARS:
        return {"type": "raw", "text": serialized, "fullChars": full_chars}
    return {
        "type": "raw",
        "text": serialized[:INSPECTOR_INLINE_BODY_CHARS].rstrip(),
        "fullChars": full_chars,
        "truncated": True,
    }


# Keys that mean "this body IS the policy decision, not a tool result".
_POLICY_ONLY_KEYS = {
    "target",
    "workspaceRoot",
    "scope",
    "accessAction",
    "policyDecision",
    "policySummary",
    "command",
    "error",
}


def _is_policy_only_body(body: dict[str, Any]) -> bool:
    """True when a blocked call's body carries nothing but its policy verdict.

    A blocked tool has no result to preview — the body is the refusal. Without
    this it fell through to `_generic_preview`, which JSON-dumped the whole
    policy object into the transcript beside a UI that already renders
    policyDecision, target, and policySummary as their own fields. The operator
    saw the same refusal twice, once as prose and once as a wall of JSON.
    """
    return bool(body) and set(body).issubset(_POLICY_ONLY_KEYS) and "policyDecision" in body


def _preview_payload(tool_id: str, body: Any) -> dict[str, Any] | None:
    if body is None:
        return None
    if not isinstance(body, dict):
        return _generic_preview(body)
    if _is_policy_only_body(body):
        return None
    if tool_id == "plan.write":
        items = body.get("items")
        if isinstance(items, list):
            clean = [
                {"content": str(i.get("content") or ""), "status": str(i.get("status") or "pending")}
                for i in items
                if isinstance(i, dict) and i.get("content")
            ]
            if clean:
                return {"type": "plan", "items": clean}
    if tool_id == "web.search":
        results = body.get("results")
        if isinstance(results, list):
            clean = [
                {
                    "title": str(r.get("title") or ""),
                    "url": str(r.get("url") or ""),
                    "snippet": str(r.get("snippet") or ""),
                }
                for r in results
                if isinstance(r, dict) and r.get("url")
            ]
            return {"type": "web_search", "query": str(body.get("query") or ""), "results": clean[:8]}
    if tool_id == "web.fetch":
        text = body.get("text")
        if isinstance(text, str):
            return {
                "type": "web_doc",
                "url": str(body.get("url") or ""),
                "title": str(body.get("title") or ""),
                "wordCount": int(body.get("wordCount") or 0),
                "text": text.rstrip()[:600],
            }
    # No market.* branch on purpose. Each of these once returned a hand-written
    # projection — market.compare emitted only the symbol list, discarding the rows
    # that were the entire point of the call — and the frontend has never had a
    # renderer for any of the five `market_*` preview types, so every market tool
    # call rendered blank in the inspector. That is precisely the failure
    # `_generic_preview` was written to prevent (see its docstring). Falling through
    # to it yields `{"type": "raw"}`, which the UI does render, bounded by
    # INSPECTOR_INLINE_BODY_CHARS with the whole body still in the tool_output
    # artifact. Do not add a projection here without shipping its renderer.
    if tool_id == "files.read":
        path = body.get("path")
        content = body.get("content")
        if isinstance(path, str) and isinstance(content, str):
            # Carry what the MODEL actually read (bounded by file_output_limit) so
            # the Inspect drawer can show the full read; the inline transcript caps
            # the DISPLAY to a 200-line teaser. Not a 240-char receipt anymore.
            preview_content = content.rstrip()[:24000]
            lines = preview_content.split("\n")
            return {
                "type": "file_read",
                "path": path,
                # `lines`, not `content`: the frontend's FileReadPreview reads an
                # array. It used to infer this shape from the presence of
                # path+content, which worked until someone renamed a field.
                "lines": lines,
                "startLine": body.get("startLine", 1),
                # Number of lines actually carried in this preview, not the
                # whole file. Inline "more lines" must never promise content
                # the Inspect drawer does not have.
                "totalLines": len(lines),
            }
    if tool_id in {"files.rg", "files.search", "files.list", "git.status", "git.diff"}:
        matches = body.get("matches")
        if isinstance(matches, list):
            return {
                "type": "repo_search",
                "query": str(body.get("pattern") or body.get("query") or ""),
                "matches": [
                    {
                        "path": str(row.get("path") or ""),
                        "line": int(row.get("line") or 0),
                        # The handler calls it `text`; the renderer calls it
                        # `snippet`. Normalize here rather than making the client
                        # accept both.
                        "snippet": str(row.get("text") or row.get("snippet") or ""),
                    }
                    for row in matches
                    if isinstance(row, dict)
                ],
                "totalMatches": body.get("totalMatches"),
            }
    if tool_id == "shell.exec":
        stdout = body.get("stdout")
        stderr = body.get("stderr")
        if isinstance(stdout, str) or isinstance(stderr, str):
            command = str(body.get("command") or "")
            streams = [str(stdout or "").rstrip(), str(stderr or "").rstrip()]
            text = "\n".join(part for part in streams if part)
            return {
                "type": "raw",
                "text": f"$ {command}\n{text}" if command else text,
                "fullChars": len(text),
            }
    if tool_id in {"files.write", "files.edit"}:
        diff = body.get("diff")
        if isinstance(diff, str) and diff.strip():
            return {
                "type": "diff",
                "path": str(body.get("path") or body.get("target") or ""),
                "diff": diff,
                "linesAdded": int(body.get("linesAdded") or 0),
                "linesRemoved": int(body.get("linesRemoved") or 0),
                "truncated": bool(body.get("diffTruncated")),
                "created": bool(body.get("created")),
                # Digest the edit left the file at — the revert key (operator can
                # undo this exact edit while the file is still in this state).
                "afterDigest": str(body.get("digest") or ""),
            }
    if tool_id in {"files.search", "files.rg"}:
        matches = body.get("matches")
        if isinstance(matches, list):
            preview_matches: list[dict[str, Any]] = []
            for item in matches[:5]:
                if not isinstance(item, dict):
                    continue
                preview_item = {
                    "path": item.get("path"),
                    "line": item.get("line"),
                    "text": item.get("text"),
                }
                if item.get("column") is not None:
                    preview_item["column"] = item.get("column")
                preview_matches.append(preview_item)
            return {"matches": preview_matches}
    if "artifactId" in body and "preview" in body:
        return {"artifactId": body.get("artifactId"), "preview": body.get("preview")}
    if tool_id == "shell.exec":
        stdout = body.get("stdout")
        stderr = body.get("stderr")
        command = body.get("command")
        parts: list[str] = []
        if isinstance(command, str) and command.strip():
            parts.append(f"$ {command.strip()}")
        if isinstance(stdout, str) and stdout.strip():
            parts.append(stdout.strip())
        if isinstance(stderr, str) and stderr.strip():
            parts.append(stderr.strip())
        if parts:
            return {"preview": "\n".join(parts)[:1000]}
    if tool_id == "artifact.create" and isinstance(body.get("title"), str):
        return {
            "artifactId": body.get("artifactId"),
            "preview": body.get("preview") or body.get("title"),
        }
    return _generic_preview(body)


def _arguments_payload(arguments: dict[str, Any]) -> tuple[dict[str, Any], dict[str, int]]:
    """Return the call arguments for the inspector, plus a map of what got clipped.

    Arguments are the half of a tool call the run record never carried: it could
    show that `files.rg` ran but not what it searched for. Keys and structure are
    always preserved so the shape of the call is never in doubt; only an oversized
    string value (a `files.write` body, a pasted blob) is clipped, and the second
    return value names every key that was and its true length — so the drawer can
    say "clipped from 91,204 chars" instead of quietly showing a partial value.
    """
    payload: dict[str, Any] = {}
    truncated: dict[str, int] = {}
    for key, value in arguments.items():
        if isinstance(value, str) and len(value) > INSPECTOR_INLINE_BODY_CHARS:
            payload[key] = value[:INSPECTOR_INLINE_BODY_CHARS].rstrip()
            truncated[key] = len(value)
            continue
        payload[key] = value
    return payload, truncated


def _batch_member_payloads(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    results = body.get("results")
    if not isinstance(results, list):
        return []
    # Only a real tool batch — where each row is itself a tool result — should
    # expand into members. Other tools (e.g. web.search) legitimately return a
    # "results" list of plain data rows; those carry no "toolId" and must NOT be
    # mistaken for failed sub-tools.
    if not any(isinstance(item, dict) and item.get("toolId") for item in results):
        return []
    rows: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        tool_id = str(item.get("toolId") or "")
        payload = {
            "toolId": tool_id,
            "ok": bool(item.get("ok")),
            "summary": str(item.get("summary") or ""),
            "error": str(item.get("error")).strip() if item.get("error") is not None else None,
        }
        output = item.get("output")
        if isinstance(output, dict):
            for key in ("target", "workspaceRoot", "scope", "accessAction", "policyDecision", "policySummary"):
                value = output.get(key)
                if value is not None:
                    payload[key] = value
        preview = _preview_payload(tool_id, item.get("output"))
        if preview is not None:
            payload["preview"] = preview
        rows.append(payload)
    return rows


def build_tool_effect_payload(
    *,
    result: ToolExecutionResult,
    arguments: dict[str, Any],
    descriptor: ToolDescriptor | None,
    turn_id: str,
    decision_id: str | None = None,
    evidence_role: ToolEvidenceRole | None = None,
) -> dict[str, Any]:
    """Return versioned UI metadata describing one completed tool effect."""
    body = result.body if result.body is not None else result.output
    role = evidence_role or (descriptor.evidence_role if descriptor is not None else "none")
    return {
        "schema_version": "tool_effect.v1",
        "effect_id": f"effect-{result.call_id}" if result.call_id else f"effect-{result.tool_id}",
        "decision_id": decision_id,
        "turn_id": turn_id,
        "tool_id": result.tool_id,
        "kind": _tool_effect_kind(result.tool_id),
        "target": _tool_effect_target(arguments=arguments, body=body),
        "preview": _preview_payload(result.tool_id, body),
        "artifact_id": result.artifact_id,
        "evidence_role": role,
    }


def _tool_effect_kind(tool_id: str) -> ToolEffectKind:
    if tool_id == "files.read":
        return "file_read"
    if tool_id in {"files.search", "files.rg", "files.list", "git.status", "git.diff", "repo.map", "test.discover"}:
        return "repo_search"
    if tool_id == "shell.exec":
        return "shell_command"
    if tool_id == "files.write":
        return "file_write"
    if tool_id == "files.edit":
        return "file_edit"
    if tool_id == "artifact.create":
        return "artifact"
    if tool_id == "web.search":
        return "web_search"
    if tool_id == "web.fetch":
        return "web_fetch"
    if tool_id in {"context.prepare", "memory.read", "memory.write", "market.dashboard", "market.ticker", "market.compare", "market.evidence", "market.financials"}:
        return "context"
    return "raw"


def _tool_effect_target(*, arguments: dict[str, Any], body: Any) -> str | None:
    for key in ("path", "target", "command", "query", "url", "pattern", "title", "symbol"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if isinstance(body, dict):
        for key in ("path", "target", "command", "query", "url", "pattern", "title"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None
