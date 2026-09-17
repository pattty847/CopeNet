"""Assemble persisted assistant text, reasoning and tool result parts."""

from __future__ import annotations

import json


def _append_text_part(parts: list[dict], text: str) -> None:
    if not text:
        return
    if parts and parts[-1].get("kind") == "text":
        parts[-1]["text"] = f"{parts[-1].get('text') or ''}{text}"
        return
    parts.append({"kind": "text", "text": text})


def _replay_output_from_runtime_input(runtime_input: object) -> str:
    """Extract the model-facing tool output string from a tool's runtime input.

    Used to persist `replayOutput` on the transcript tool_result part so a later
    turn replays the real output (file contents, command stdout, ...) rather than
    just the one-line summary. Bounded already by the artifact mechanism.
    """
    if not isinstance(runtime_input, dict):
        return ""
    body = runtime_input.get("body")
    if isinstance(body, str):
        return body
    if isinstance(body, (dict, list)):
        try:
            return json.dumps(body, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(body)
    summary = runtime_input.get("summary")
    return str(summary) if isinstance(summary, str) else ""


def _append_thinking_part(parts: list[dict], text: str, *, source: str = "summary") -> None:
    if not text:
        return
    if parts and parts[-1].get("kind") == "thinking" and parts[-1].get("source", "summary") == source:
        parts[-1]["text"] = f"{parts[-1].get('text') or ''}{text}"
        return
    parts.append({"kind": "thinking", "text": text, "source": source})


def _normalize_final_message_parts(parts: list[dict], *, assistant_text: str) -> list[dict]:
    """Return the persisted parts in the order the run produced them.

    Narration between tool calls stays where it happened: the thread renders a
    reloaded turn the same way it streamed, and cross-turn replay sees each text
    in its real position. This used to fold the whole answer into the first text
    part, which moved the final answer ahead of every tool call on reload.
    """
    normalized = [dict(part) for part in parts]
    if assistant_text and not any(part.get("kind") == "text" for part in normalized):
        normalized.append({"kind": "text", "text": assistant_text})
    return normalized
