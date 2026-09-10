"""Tool inspector previews and effect projections."""

from __future__ import annotations
import json
from typing import Any, TYPE_CHECKING
from .preview_builders import PREVIEW_BUILDERS

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
    if isinstance(body, dict):
        if _is_policy_only_body(body):
            return None
        builder = PREVIEW_BUILDERS.get(tool_id)
        if builder is not None:
            preview = builder(body)
            if preview is not None:
                return preview
    # Raw is the declared, bounded representation for every unspecialized tool,
    # including Market and artifact results. Never return an untyped shape.
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
            for key in (
                "target",
                "workspaceRoot",
                "scope",
                "accessAction",
                "policyDecision",
                "policySummary",
            ):
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
    if tool_id in {"files.rg", "git.status", "git.diff", "repo.map", "test.discover"}:
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
    if tool_id in {
        "memory.read",
        "memory.write",
        "market.dashboard",
        "market.ticker",
        "market.compare",
        "market.evidence",
        "market.financials",
    }:
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
