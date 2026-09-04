"""Real multi-turn message-history assembly for CopeNet runs.

Phase 1 of HARNESS_REBUILD_V2.md. Replaces the synthetic `assemble_working_set`
blob (keyword-scaffolded single-string prompt) with a proper Responses-API
`messages[]` array built directly from the durable transcript.

Two outputs:
- `build_chat_messages(...)` -> the structured `messages[]` array. Used directly
  by the Phase 2 Responses-native tool loop, and as the source for the prompt
  flattener below.
- `flatten_messages_to_prompt(...)` -> a clean transcript-style prompt string for
  providers that still take a single `prompt: str` (claude-cli / openai-codex /
  LM Studio / Ollama prompted path). This preserves true multi-turn continuity
  for those providers too, instead of the old amnesiac working-set blob.

No keyword extraction. No session-state synthesis. Just transcript -> API items.
"""

from __future__ import annotations

import json
from typing import Any

from copenet.core.harness import responses_items
from copenet.core.harness.context_window import (
    estimate_input_tokens,
    trim_messages_to_token_budget,
)


def build_chat_messages(
    *,
    transcript_messages: list[dict[str, Any]],
    current_user_message: str,
    max_context_tokens: int | None = None,
    current_user_image_parts: list[dict[str, Any]] | None = None,
    attachment_resolver: responses_items.AttachmentResolver | None = None,
) -> list[dict[str, Any]]:
    """Walk transcript parts and produce a Responses-API input array.

    `transcript_messages` are the durable history rows (role/content/parts/run_id)
    in chronological order, EXCLUDING the current user message — that is appended
    last from `current_user_message`.

    `current_user_image_parts` carry the live turn's image attachments as
    `input_image` parts; `attachment_resolver` re-inlines images for past user
    turns so multi-turn vision survives replay.

    When `max_context_tokens` is set, oldest complete conversation turns are
    omitted from the provider view. Durable transcript storage is untouched.
    """
    messages = responses_items.transcript_to_input_array(
        transcript_messages=_with_chart_references(transcript_messages),
        current_user_message=current_user_message,
        current_user_image_parts=current_user_image_parts,
        attachment_resolver=attachment_resolver,
    )
    if max_context_tokens is None:
        return messages
    return trim_messages_to_token_budget(messages, max_context_tokens=max_context_tokens)


def flatten_messages_to_prompt(messages: list[dict[str, Any]]) -> str:
    """Serialize a Responses messages[] array into a transcript-style prompt string.

    For prompt-only providers. The final user message is rendered under a
    "Current user request" header so the model can distinguish the live ask from
    replayed history. Prior turns are rendered as a labeled conversation log.
    """
    if not messages:
        return ""
    # The last user_input item is the live request; everything before is history.
    last_user_index = _last_user_index(messages)
    history_lines: list[str] = []
    for index, item in enumerate(messages):
        if index == last_user_index:
            continue
        rendered = _render_history_item(item)
        if rendered:
            history_lines.append(rendered)

    sections: list[str] = []
    if history_lines:
        sections.append("Conversation so far:\n" + "\n".join(history_lines))
    if last_user_index is not None:
        current = _user_item_text(messages[last_user_index])
        if current:
            sections.append(f"Current user request:\n{current}")
    return "\n\n".join(section for section in sections if section.strip())


# -- Helpers --------------------------------------------------------------------


def _last_user_index(messages: list[dict[str, Any]]) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user" and "content" in messages[index]:
            return index
    return None


def _user_item_text(item: dict[str, Any]) -> str:
    parts = item.get("content")
    if isinstance(parts, list):
        return " ".join(
            str(p.get("text") or "") for p in parts if isinstance(p, dict)
        ).strip()
    return str(item.get("content") or "").strip()


def _render_history_item(item: dict[str, Any]) -> str:
    item_type = item.get("type")
    role = item.get("role")
    if role == "user" and item_type is None:
        text = _user_item_text(item)
        return f"user: {text}" if text else ""
    if item_type == "message" and role == "assistant":
        text = " ".join(
            str(p.get("text") or "")
            for p in (item.get("content") or [])
            if isinstance(p, dict)
        ).strip()
        return f"assistant: {text}" if text else ""
    if item_type == "function_call":
        name = item.get("name") or "tool"
        args = item.get("arguments") or "{}"
        return f"assistant called {name}({args})"
    if item_type == "function_call_output":
        output = str(item.get("output") or "").strip()
        # Keep tool outputs bounded in the flattened prompt; the structured
        # messages[] path (Phase 2) sends the full thing.
        if len(output) > 2000:
            output = output[:2000] + " …[truncated]"
        return f"tool result: {output}" if output else ""
    return ""


def _with_chart_references(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Replay immutable attribution, never expand an old observation into raw data."""
    rows = []
    for row in messages:
        reference = row.get("marketContext") or row.get("market_context")
        if reference and row.get("role") == "user":
            row = {**row, "content": row.get("content", "") + "\nHistorical chart observation: " + json.dumps(reference, separators=(",", ":"))}
        if reference and row.get("parts"):
            parts = []
            for part in row["parts"]:
                execution = part.get("toolExecution")
                if part.get("kind") == "tool_result" and execution and execution.get("toolId", "").startswith("market.chart."):
                    replay = {"summary": execution.get("summary"), "ok": execution.get("ok"),
                              "artifactId": execution.get("artifactId"), "marketContext": reference,
                              "notice": "Historical chart result; exact evidence is retained in the observation store. Re-read within current scope if needed."}
                    part = {**part, "toolExecution": {**execution, "replayOutput": json.dumps(replay, separators=(",", ":"))}}
                parts.append(part)
            row = {**row, "parts": parts}
        rows.append(row)
    return rows
