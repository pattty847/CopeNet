"""Tool-result artifact materialization helpers for harness loops."""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from uuid import uuid4

from copenet.core.tools import ToolExecutionContext, ToolExecutionResult


TraceRecorder = Callable[[str, dict[str, Any] | None], None]
# Above this size, a tool result is also persisted as an artifact (for the UI).
LARGE_TOOL_RESULT_CHAR_LIMIT = 4000

# How much ACTUAL tool-output text the MODEL receives when a result is persisted.
# The full output is always saved as an artifact for the UI; this caps only what
# is fed back into the model's context, so a huge file can't blow the token
# budget — while still being REAL content, not a 280-char receipt the agent
# can't act on (the friction a phone-driven self-inspection surfaced). The tool
# handlers already truncate their own output (files.read ~12KB, shell ~8-20KB),
# so this is mostly a backstop. Override with COPNET_MODEL_TOOL_RESULT_CHARS.
#
# Default chosen to match Claude Code's Bash-output default (30,000 chars; their
# hard ceiling via BASH_MAX_OUTPUT_LENGTH is 150,000). Their file Read is
# token-aware (no char cap) — set COPNET_MODEL_TOOL_RESULT_CHARS higher if you
# want to lean that way; lower it on a phone to save tokens.
_DEFAULT_MODEL_FACING_RESULT_CHARS = 30000


def model_facing_result_char_limit() -> int:
    """Max chars of a persisted tool result fed back to the model (env-overridable)."""
    raw = os.environ.get("COPNET_MODEL_TOOL_RESULT_CHARS", "").strip()
    if raw:
        try:
            value = int(raw)
        except ValueError:
            value = 0
        if value > 0:
            return value
    return _DEFAULT_MODEL_FACING_RESULT_CHARS


def _materialize_tool_result_artifact(
    *,
    tool_result: ToolExecutionResult,
    tool_context: ToolExecutionContext,
    trace: TraceRecorder | None,
) -> tuple[ToolExecutionResult, dict[str, Any] | None]:
    body = tool_result.body if tool_result.body is not None else tool_result.output
    payload_text = json.dumps(body, ensure_ascii=False, indent=2) if not isinstance(body, str) else body
    if not payload_text.strip():
        normalized = ToolExecutionResult(
            tool_id=tool_result.tool_id,
            call_id=tool_result.call_id,
            channel=tool_result.channel,
            ok=tool_result.ok,
            summary=tool_result.summary,
            body=f"({tool_result.tool_id} completed with no output)",
            output=dict(tool_result.output),
            error=tool_result.error,
            artifact_id=tool_result.artifact_id,
        )
        return normalized, None
    if len(payload_text) <= LARGE_TOOL_RESULT_CHAR_LIMIT or tool_context.artifact_store is None or not tool_context.session_key:
        if trace is not None and tool_result.call_id:
            trace(
                "tool_result_normalized",
                {
                    "toolId": tool_result.tool_id,
                    "callId": tool_result.call_id,
                    "channel": tool_result.channel,
                    "success": tool_result.ok,
                },
            )
        return tool_result, None

    artifact = tool_context.artifact_store.create(
        session_key=tool_context.session_key,
        run_id=tool_result.call_id or f"tool-{uuid4().hex[:8]}",
        artifact_type="tool_output",
        title=f"{tool_result.tool_id} output",
        body=payload_text,
        metadata={
            "toolId": tool_result.tool_id,
            "callId": tool_result.call_id,
            "channel": tool_result.channel,
            "persistedOutput": True,
        },
    )
    # Hand the MODEL real content (up to the budget), not a 280-char receipt. The
    # full output is in the artifact above; the model gets the actual text so it
    # can actually use the result. Keep the structured body when it fits; only
    # clip (to a string + continuation pointer) when it genuinely exceeds budget.
    model_limit = model_facing_result_char_limit()
    if len(payload_text) <= model_limit:
        base = dict(body) if isinstance(body, dict) else {"content": body}
        persisted_body = {**base, "artifactId": artifact.artifact_id, "persistedOutput": True}
    else:
        clipped = payload_text[:model_limit].rstrip()
        persisted_body = {
            "content": clipped,
            "artifactId": artifact.artifact_id,
            "persistedOutput": True,
            "truncatedForModel": True,
            "fullChars": len(payload_text),
            "continuationHint": (
                f"Showing the first {model_limit} of {len(payload_text)} characters. The full output is "
                f"saved as artifact {artifact.artifact_id}. For a file read, continue by calling files.read "
                f"again — with a higher offset, or with start_line/end_line to read a specific range."
            ),
        }
    persisted = ToolExecutionResult(
        tool_id=tool_result.tool_id,
        call_id=tool_result.call_id,
        channel=tool_result.channel,
        ok=tool_result.ok,
        summary=tool_result.summary,
        body=persisted_body,
        output=dict(tool_result.output),
        error=tool_result.error,
        artifact_id=artifact.artifact_id,
    )
    if trace is not None:
        trace(
            "tool_result_persisted",
            {
                "toolId": tool_result.tool_id,
                "callId": tool_result.call_id,
                "artifactId": artifact.artifact_id,
            },
        )
    return persisted, None
