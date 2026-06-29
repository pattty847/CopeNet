"""Canonical Responses API item shapes for the CopeNet harness.

These are the exact shapes accepted by the chatgpt.com/backend-api/codex/responses
endpoint, verified against live probe data captured in PASS-7
(docs/investigations/harness-rebuild/probe-results/).

Used by:
- Phase 1: build_chat_messages() walks transcript parts and emits these items
  as a multi-turn input[] array.
- Phase 2: run_with_responses_tools handles function_call streaming events and
  appends function_call_output items to the running input[] across iterations.

Item types:
- user input         {role: "user", content: [{type: "input_text", text}]}
- assistant message  {type: "message", role: "assistant", id, content: [...], status}
- function call      {type: "function_call", id, call_id, name, arguments}
- function call out  {type: "function_call_output", call_id, output}
"""

from __future__ import annotations

import json
from typing import Any, Callable, TypedDict


# Resolves a transcript message's stored attachment refs (list of dicts carrying
# `attachmentId`) into Responses `input_image` content parts. Injected by the
# orchestrator so this module stays free of storage dependencies.
AttachmentResolver = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


# -- Item dict shapes (TypedDict for readability; runtime values are plain dicts) -


class UserInputItem(TypedDict):
    role: str
    content: list[dict[str, str]]


class AssistantMessageItem(TypedDict):
    type: str
    role: str
    id: str
    content: list[dict[str, Any]]
    status: str


class FunctionCallItem(TypedDict):
    type: str
    id: str
    call_id: str
    name: str
    arguments: str


class FunctionCallOutputItem(TypedDict):
    type: str
    call_id: str
    output: str


# -- Item builders --------------------------------------------------------------


def image_content_part(image_url: str) -> dict[str, Any]:
    """One `input_image` content part for the Responses/codex backend.

    `image_url` is a base64 data URL (`data:<mime>;base64,<...>`) or an http(s)
    URL. `detail: "auto"` matches the reference (openclaw) shape the codex backend
    accepts.
    """
    return {"type": "input_image", "detail": "auto", "image_url": image_url}


def user_input_item(text: str, image_parts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One user-authored message in the input[] array.

    Text is always present (kept first so prompt-flattening still finds it). Any
    `image_parts` (already-built `input_image` content parts) are appended, which
    is how attachments reach a vision-capable model.
    """
    content: list[dict[str, Any]] = [{"type": "input_text", "text": text}]
    if image_parts:
        content.extend(image_parts)
    return {
        "role": "user",
        "content": content,
    }


def assistant_message_item(message_id: str, text: str) -> dict[str, Any]:
    """One assistant text response in the input[] array."""
    return {
        "type": "message",
        "role": "assistant",
        "id": message_id,
        "content": [{"type": "output_text", "text": text, "annotations": []}],
        "status": "completed",
    }


def function_call_item(*, item_id: str, call_id: str, name: str, arguments: dict[str, Any] | str) -> dict[str, Any]:
    """One assistant-emitted tool call. `arguments` is serialized to JSON string."""
    args_str = arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False)
    # Keep the canonical (dotted) tool id here so the flattened-prompt path and
    # transcript-derived display stay accurate. The Responses provider sanitizes
    # function names (dots are illegal there) at the API boundary on send.
    return {
        "type": "function_call",
        "id": item_id,
        "call_id": call_id,
        "name": name,
        "arguments": args_str,
    }


def function_call_output_item(*, call_id: str, output: str | dict[str, Any]) -> dict[str, Any]:
    """One tool result paired to a prior function_call by call_id."""
    output_str = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    return {
        "type": "function_call_output",
        "call_id": call_id,
        "output": output_str,
    }


# -- Transcript walking ---------------------------------------------------------


def parts_to_response_items(parts: list[dict[str, Any]], *, run_id: str) -> list[dict[str, Any]]:
    """Convert one assistant transcript message's parts list into Responses items.

    A single assistant turn can contain interleaved text, tool_call, and tool_result
    parts. Each becomes its own item in order. Synthetic message ids are stable
    per (run_id, part_index) so a re-walk produces identical input[].

    function_call and function_call_output items must share a call_id. The
    runtime stamps a matching callId on both the tool_call and tool_result parts,
    but to stay robust against older transcripts (where only the tool_result
    carried a callId), we pair tool_call -> tool_result positionally: the k-th
    valid tool_call binds to the k-th tool_result, and they share whichever
    callId is present (preferring the tool_result's, then the tool_call's, then
    a synthesized id). A tool_call with no toolId/name is dropped (no valid
    function to emit), and its paired tool_result is dropped with it.
    """
    # First pass: positionally pair tool_call <-> tool_result and resolve a
    # shared call_id per pair.
    call_indices = [i for i, p in enumerate(parts) if p.get("kind") == "tool_call"]
    result_indices = [i for i, p in enumerate(parts) if p.get("kind") == "tool_result"]
    shared_call_id: dict[int, str] = {}
    dropped: set[int] = set()
    for pair_num, call_index in enumerate(call_indices):
        tc = parts[call_index].get("toolCall") or {}
        name = str(tc.get("toolId") or "").strip()
        result_index = result_indices[pair_num] if pair_num < len(result_indices) else None
        if not name:
            # No function name -> cannot emit a function_call; drop the call and
            # its paired result.
            dropped.add(call_index)
            if result_index is not None:
                dropped.add(result_index)
            continue
        te = parts[result_index].get("toolExecution") or {} if result_index is not None else {}
        call_id = (
            str(te.get("callId") or "").strip()
            or str(tc.get("callId") or "").strip()
            or f"call_{run_id}_{pair_num}"
        )
        shared_call_id[call_index] = call_id
        if result_index is not None:
            shared_call_id[result_index] = call_id

    items: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        if index in dropped:
            continue
        kind = part.get("kind")
        if kind == "text":
            text = str(part.get("text") or part.get("content") or "").strip()
            if not text:
                continue
            items.append(assistant_message_item(message_id=f"msg_{run_id}_{index}", text=text))
        elif kind == "tool_call":
            tc = part.get("toolCall") or {}
            name = str(tc.get("toolId") or "").strip()
            call_id = shared_call_id.get(index)
            if not name or not call_id:
                continue
            items.append(
                function_call_item(
                    item_id=f"fc_{run_id}_{index}",
                    call_id=call_id,
                    name=name,
                    arguments=tc.get("arguments") or {},
                )
            )
        elif kind == "tool_result":
            te = part.get("toolExecution") or {}
            call_id = shared_call_id.get(index) or str(te.get("callId") or "").strip()
            if not call_id:
                continue
            items.append(
                function_call_output_item(
                    call_id=call_id,
                    output=_tool_output_for_replay(te),
                )
            )
    return items


def transcript_to_input_array(
    *,
    transcript_messages: list[dict[str, Any]],
    current_user_message: str,
    current_user_image_parts: list[dict[str, Any]] | None = None,
    attachment_resolver: AttachmentResolver | None = None,
) -> list[dict[str, Any]]:
    """Walk a session's full transcript and emit the input[] array for the next turn.

    Yields user input items for past user messages, plus the assistant-side items
    (text + tool calls + tool outputs) interleaved in their original order, finally
    appending the new user message.

    `current_user_image_parts` are `input_image` parts for the live turn's
    attachments. `attachment_resolver`, when provided, re-inlines images for PAST
    user turns that carried attachments — keeping multi-turn vision intact (ask a
    follow-up about an image uploaded several turns ago).
    """
    items: list[dict[str, Any]] = []
    for message in transcript_messages:
        role = str(message.get("role") or "").strip()
        if role == "user":
            content = str(message.get("content") or "").strip()
            past_image_parts: list[dict[str, Any]] = []
            refs = message.get("attachments")
            if attachment_resolver is not None and isinstance(refs, list) and refs:
                past_image_parts = attachment_resolver(refs)
            if content or past_image_parts:
                items.append(user_input_item(content, past_image_parts or None))
        elif role == "assistant":
            parts = message.get("parts")
            run_id = str(message.get("run_id") or message.get("runId") or "unknown")
            if isinstance(parts, list) and parts:
                items.extend(parts_to_response_items(parts, run_id=run_id))
            else:
                # No structured parts — fall back to whatever text content exists.
                content = str(message.get("content") or "").strip()
                if content:
                    items.append(assistant_message_item(message_id=f"msg_{run_id}", text=content))
    items.append(user_input_item(current_user_message, current_user_image_parts))
    return items


# -- Helpers --------------------------------------------------------------------


def _tool_output_for_replay(tool_execution: dict[str, Any]) -> str:
    """Serialize a tool execution payload into the string the model should see on replay.

    The UI consumes the rich ToolExecutionResult (summary, body, output dict, etc.);
    the model needs a single string. Prefer body, fall back to summary, then output.
    """
    # replayOutput is the actual tool output (file contents, stdout, ...) the
    # runtime persisted specifically for cross-turn replay. Prefer it over the
    # one-line summary so the model keeps what it saw in earlier turns.
    replay_output = tool_execution.get("replayOutput")
    if isinstance(replay_output, str) and replay_output.strip():
        return replay_output
    body = tool_execution.get("body")
    if isinstance(body, str) and body.strip():
        return body
    if isinstance(body, (dict, list)):
        return json.dumps(body, ensure_ascii=False, indent=2)
    summary = tool_execution.get("summary")
    if isinstance(summary, str) and summary.strip():
        return summary
    output = tool_execution.get("output")
    if isinstance(output, (dict, list)):
        return json.dumps(output, ensure_ascii=False, indent=2)
    if isinstance(output, str):
        return output
    return ""
