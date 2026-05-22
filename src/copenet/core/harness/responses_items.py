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
from typing import Any, TypedDict


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


def user_input_item(text: str) -> dict[str, Any]:
    """One user-authored message in the input[] array."""
    return {
        "role": "user",
        "content": [{"type": "input_text", "text": text}],
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
    """
    items: list[dict[str, Any]] = []
    for index, part in enumerate(parts):
        kind = part.get("kind")
        if kind == "text":
            text = str(part.get("text") or part.get("content") or "").strip()
            if not text:
                continue
            items.append(assistant_message_item(message_id=f"msg_{run_id}_{index}", text=text))
        elif kind == "tool_call":
            tc = part.get("toolCall") or {}
            call_id = str(tc.get("callId") or "").strip()
            name = str(tc.get("toolId") or "").strip()
            if not call_id or not name:
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
            call_id = str(te.get("callId") or "").strip()
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
) -> list[dict[str, Any]]:
    """Walk a session's full transcript and emit the input[] array for the next turn.

    Yields user input items for past user messages, plus the assistant-side items
    (text + tool calls + tool outputs) interleaved in their original order, finally
    appending the new user message.
    """
    items: list[dict[str, Any]] = []
    for message in transcript_messages:
        role = str(message.get("role") or "").strip()
        if role == "user":
            content = str(message.get("content") or "").strip()
            if content:
                items.append(user_input_item(content))
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
    items.append(user_input_item(current_user_message))
    return items


# -- Helpers --------------------------------------------------------------------


def _tool_output_for_replay(tool_execution: dict[str, Any]) -> str:
    """Serialize a tool execution payload into the string the model should see on replay.

    The UI consumes the rich ToolExecutionResult (summary, body, output dict, etc.);
    the model needs a single string. Prefer body, fall back to summary, then output.
    """
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
