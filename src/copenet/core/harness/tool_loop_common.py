"""Shared helpers for CopeNet harness tool loops."""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Awaitable, Callable
from uuid import uuid4

from copenet.core.tools import ToolDescriptor, ToolExecutionContext, ToolExecutionRequest, ToolExecutionResult
from copenet.providers import Provider, ProviderEvent

from .planning import HarnessTurnPlan


ToolExecutor = Callable[[ToolExecutionRequest, ToolExecutionContext], Awaitable[ToolExecutionResult]]
TraceRecorder = Callable[[str, dict[str, Any] | None], None]
# Frontier harnesses leave step-count to the model. 100 is high enough that
# real work never hits it, low enough that runaway loops eventually stop.
MAX_TOOL_STEPS = 100
# A long tool-heavy turn (e.g. deep web research) re-sends its whole growing
# message list to the provider on every step — every full-size web.fetch dump
# from step 3 gets reprocessed (and billed) again on steps 4 through 20. Only
# the most recent N tool results stay full-size on replay; older ones are
# compacted to a short identifying stub (see _compact_tool_output_text). This
# never touches what CopeNet persists to the transcript — only the outbound
# view sent to the provider.
KEEP_RECENT_TOOL_RESULTS = 6
TOOL_OUTPUT_COMPACT_CHARS = 600
# Default reasoning config for the native Responses path. summary="auto" is
# the gate that makes the endpoint stream response.reasoning_summary_text.delta
# events — the Phase 4 inline-thinking UX. Verified live against
# chatgpt.com/backend-api/codex (gpt-5.5) via scripts/codex_responses_probe.py
# scenario E: 68 reasoning deltas on a substantive prompt. Counter-intuitively,
# adding include=["reasoning.encrypted_content"] SUPPRESSES streamed summaries
# at the "auto" level (probe scenario F: zero deltas) — only "detailed"
# overrides that suppression. We want lightweight thinking ticks, not richer
# rationales, so we stay on auto + omit include.
DEFAULT_RESPONSES_REASONING: dict[str, Any] = {"effort": "medium", "summary": "auto"}


def _max_step_explanation() -> str:
    return (
        f"[Stopped after MAX_TOOL_STEPS={MAX_TOOL_STEPS} tool calls. "
        "Returning what was produced so far.]"
    )


async def collect_provider_turn(
    *,
    provider: Provider,
    prompt: str,
    provider_session_id: str | None,
    abort_event: asyncio.Event,
    model: str | None,
    system_prompt: str | None,
    trace: TraceRecorder | None = None,
    phase: str = "provider",
) -> tuple[list[ProviderEvent], str | None]:
    """Collect one provider turn into memory for callers that need a buffered turn."""
    events: list[ProviderEvent] = []
    discovered = provider_session_id
    if trace is not None:
        trace("provider_turn_started", {"phase": phase, "providerSessionId": provider_session_id})
    async for event in provider.run(
        prompt=compose_provider_prompt(provider, prompt, system_prompt),
        provider_session_id=provider_session_id,
        abort_event=abort_event,
        model=model,
        system_prompt=provider_system_prompt(provider, system_prompt),
    ):
        if event.provider_session_id:
            discovered = event.provider_session_id
        events.append(event)
        if event.kind == "final":
            break
    if trace is not None:
        trace(
            "provider_turn_completed",
            {
                "phase": phase,
                "providerSessionId": discovered,
                "deltaCount": sum(1 for event in events if event.kind == "delta"),
            },
        )
    return events, discovered


def _tool_call_event_payload(
    *,
    tool_id: str,
    arguments: dict[str, Any],
    step: int,
    turn_id: str | None = None,
    decision_id: str | None = None,
    channel: str = "tool",
    native: bool = False,
    call_id: str | None = None,
) -> dict[str, Any]:
    hint = None
    for key in ("path", "query", "pattern", "file", "dir", "uri"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            hint = value.strip()
            break
    payload = {
        "toolId": tool_id,
        "arguments": dict(arguments),
        "target": hint,
        "hint": hint,
        "step": step,
        "channel": channel,
        "native": native,
    }
    # callId is stamped at request time (pre-execution) so the tool_call
    # transcript part shares an id with its paired tool_result. This is what
    # lets responses_items pair function_call <-> function_call_output on replay.
    if call_id:
        payload["callId"] = call_id
    if turn_id:
        payload["turnId"] = turn_id
    if decision_id:
        payload["decisionId"] = decision_id
    return payload


def _tool_result_event_payload(
    *,
    result: ToolExecutionResult,
    request: ToolExecutionRequest,
    plan: HarnessTurnPlan,
) -> dict[str, Any]:
    descriptor = next((tool for tool in plan.tools if tool.id == result.tool_id), None)
    return result.to_event_payload(
        turn_id=plan.turn_id,
        decision_id=plan.decision_id,
        arguments=request.arguments,
        evidence_role=descriptor.evidence_role if descriptor is not None else "none",
    )


def _extract_native_choice(response: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Native tool provider returned no choices.")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise RuntimeError("Native tool provider returned an invalid choice payload.")
    message = choice.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("Native tool provider returned no assistant message.")
    finish_reason = choice.get("finish_reason")
    return message, str(finish_reason).strip() if finish_reason is not None else None


def _coerce_native_message_content(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _extract_native_tool_calls(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        function = item.get("function")
        if not isinstance(function, dict):
            continue
        call_id = str(item.get("id") or "").strip() or f"call-{uuid4().hex[:10]}"
        name = str(function.get("name") or "").strip()
        if not name:
            continue
        rows.append(
            {
                "id": call_id,
                "type": "function",
                "function": {
                    "name": name,
                    "arguments": function.get("arguments"),
                },
            }
        )
    return rows


def _parse_native_tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _native_tool_message_content(tool_result: ToolExecutionResult) -> str:
    body = tool_result.body if tool_result.body is not None else tool_result.output
    if isinstance(body, str):
        return body
    return json.dumps(body, ensure_ascii=False, indent=2)


def _compact_tool_output_text(raw: str, *, max_chars: int = TOOL_OUTPUT_COMPACT_CHARS) -> str:
    """Shrink a stale tool result string for replay to the provider.

    Recognizes web.fetch/web.search shapes and keeps their identifying fields
    (url, title, word count, top results) so the model knows what it already
    looked at without needing to re-fetch just to remember. Anything else falls
    back to a head-truncation with an explicit note. Never called on the copy
    CopeNet persists — only on the outbound message view built per provider call.
    """
    if len(raw) <= max_chars:
        return raw
    note = (
        f"[full result was {len(raw)} chars; compacted for context budget after "
        "several more tool calls — re-fetch the same URL/query if the full "
        "content is still needed]"
    )
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        if isinstance(parsed.get("text"), str):  # web.fetch shape
            compact = {
                "url": parsed.get("url"),
                "title": parsed.get("title"),
                "wordCount": parsed.get("wordCount"),
                "excerpt": parsed.get("excerpt") or str(parsed.get("text") or "")[:280],
                "note": note,
            }
            return json.dumps(compact, ensure_ascii=False)
        if isinstance(parsed.get("results"), list):  # web.search shape
            compact = {
                "query": parsed.get("query"),
                "resultCount": len(parsed["results"]),
                "topResults": [
                    {"title": item.get("title"), "url": item.get("url")}
                    for item in parsed["results"][:3]
                    if isinstance(item, dict)
                ],
                "note": note,
            }
            return json.dumps(compact, ensure_ascii=False)
    return raw[:max_chars].rstrip() + "\n" + note


def compact_stale_responses_items(
    items: list[dict[str, Any]], *, keep_recent: int = KEEP_RECENT_TOOL_RESULTS
) -> list[dict[str, Any]]:
    """Compact all but the most recent `keep_recent` function_call_output items.

    Returns the same list object unchanged when nothing is stale yet, so callers
    with short histories pay no cost and existing exact-match tests are unaffected.
    """
    output_indices = [index for index, item in enumerate(items) if item.get("type") == "function_call_output"]
    stale_count = len(output_indices) - keep_recent
    if stale_count <= 0:
        return items
    stale_indices = set(output_indices[:stale_count])
    compacted: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        if index in stale_indices and isinstance(item.get("output"), str):
            new_item = dict(item)
            new_item["output"] = _compact_tool_output_text(item["output"])
            compacted.append(new_item)
        else:
            compacted.append(item)
    return compacted


def compact_stale_chat_messages(
    messages: list[dict[str, Any]], *, keep_recent: int = KEEP_RECENT_TOOL_RESULTS
) -> list[dict[str, Any]]:
    """Same idea as compact_stale_responses_items for OpenAI-compatible `role: "tool"` messages."""
    tool_indices = [index for index, message in enumerate(messages) if message.get("role") == "tool"]
    stale_count = len(tool_indices) - keep_recent
    if stale_count <= 0:
        return messages
    stale_indices = set(tool_indices[:stale_count])
    compacted: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        if index in stale_indices and isinstance(message.get("content"), str):
            new_message = dict(message)
            new_message["content"] = _compact_tool_output_text(message["content"])
            compacted.append(new_message)
        else:
            compacted.append(message)
    return compacted


def compose_prompted_tool_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
    tools: list[ToolDescriptor],
) -> str | None:
    tool_lines = []
    for tool in tools:
        schema = json.dumps(tool.input_schema, ensure_ascii=False, sort_keys=True)
        tool_lines.append(f"- {tool.id}: {tool.description} Schema: {schema}")
    extra = (
        "You may request CopeNet tools by outputting only JSON objects, one object per tool call, when a tool is needed.\n"
        "Use this shape: {\"tool_id\":\"shell.exec\",\"arguments\":{\"command\":\"pwd\"}}.\n"
        "For shell commands, use one command per call. Do not use pipes, chaining, redirection, or multiple commands.\n"
        "If you output {\"command\":\"pwd\"}, CopeNet will treat it as shell.exec.\n"
        "After tool results are returned, answer using the observed output.\n\n"
        "Available tools:\n"
        + "\n".join(tool_lines)
    )
    return compose_system_prompt(provider=provider, system_prompt=system_prompt, extra_instructions=extra)


def _extract_prompted_tool_requests(text: str) -> list[ToolExecutionRequest]:
    decoder = json.JSONDecoder()
    requests: list[ToolExecutionRequest] = []
    index = 0
    while index < len(text):
        start = text.find("{", index)
        if start == -1:
            break
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            index = start + 1
            continue
        index = start + max(end, 1)
        request = _coerce_prompted_tool_request(value)
        if request is not None:
            requests.append(request)
    return requests


def _coerce_prompted_tool_request(value: Any) -> ToolExecutionRequest | None:
    if not isinstance(value, dict):
        return None
    raw_tool_id = value.get("tool_id") or value.get("toolId") or value.get("name")
    arguments = value.get("arguments")
    if raw_tool_id is None and isinstance(value.get("command"), str):
        return ToolExecutionRequest(tool_id="shell.exec", arguments={"command": str(value["command"])})
    tool_id = str(raw_tool_id or "").strip()
    if not tool_id:
        return None
    if not isinstance(arguments, dict):
        arguments = {key: item for key, item in value.items() if key not in {"tool_id", "toolId", "name"}}
    return ToolExecutionRequest(tool_id=tool_id, arguments=dict(arguments))


def _compose_prompted_tool_followup(*, user_prompt: str, assistant_text: str, tool_payloads: list[str]) -> str:
    return (
        "Continue the same task using the CopeNet tool results below. "
        "Do not repeat tool calls whose results are already provided unless another command is necessary.\n\n"
        f"Original user request:\n{user_prompt}\n\n"
        f"Assistant tool request text:\n{assistant_text}\n\n"
        "Tool results:\n"
        + "\n\n".join(tool_payloads)
        + "\n\nAnswer the user in plain text when you have enough information, "
        "or request another tool with JSON if you need more."
    )


def _force_call_id(result: ToolExecutionResult, call_id: str) -> ToolExecutionResult:
    """Stamp a pre-generated call_id so the tool_call/tool_result parts pair up."""
    if result.call_id == call_id:
        return result
    return ToolExecutionResult(
        tool_id=result.tool_id,
        call_id=call_id,
        channel=result.channel,
        ok=result.ok,
        summary=result.summary,
        body=result.body,
        output=dict(result.output),
        error=result.error,
        artifact_id=result.artifact_id,
    )


def _new_call_id(tool_id: str) -> str:
    return f"{tool_id}-{uuid4().hex[:10]}"


def compose_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
    extra_instructions: str | None = None,
) -> str | None:
    del provider
    parts = [part.strip() for part in (system_prompt or "", extra_instructions or "") if part and part.strip()]
    if not parts:
        return None
    return "\n\n".join(parts)


def compose_native_tool_system_prompt(
    *,
    provider: Provider,
    system_prompt: str | None,
) -> str | None:
    return compose_system_prompt(
        provider=provider,
        system_prompt=system_prompt,
        extra_instructions=(
            "Use provider-native tools when they help. "
            "Answer in plain text when ready."
        ),
    )


def compose_responses_tool_instructions(
    *,
    system_prompt: str | None,
    workdir: str | None,
    tools: list[ToolDescriptor],
) -> str:
    """Agent instructions for the native Responses tool loop.

    The native `tools` array alone isn't enough: without an explicit agent
    directive, gpt-5.5 hedges ("I can't read files / I'm constrained not to call
    them") instead of calling the tools it was given (observed live). This tells
    the model it operates in a REAL workspace and must use its tools to act.
    """
    tool_ids = ", ".join(tool.id for tool in tools) or "(none)"
    location = f" rooted at {workdir}" if workdir else ""
    directive = (
        f"You are CopeNet's coding agent operating in a REAL workspace{location}. "
        f"You have working tools: {tool_ids}. Use them to do the task yourself — "
        "read files with files.read, search with files.rg, run commands with "
        "shell.exec. Do NOT ask the user to paste file contents and do NOT claim "
        "you lack file access or are constrained from calling tools; call the "
        "tools directly, gather what you need, then give your answer."
    )
    if any(tool.id == "plan.write" for tool in tools):
        directive += (
            " Use plan.write when a task is genuinely complex and tracking steps helps — lay out the "
            "plan first, then update it to mark steps in_progress and completed as you work. Keep exactly "
            "one step in_progress at a time. Skip it when the task is straightforward enough that a "
            "checklist adds no value."
        )
    if any(tool.id == "web.search" for tool in tools):
        directive += (
            " When a question depends on facts outside this repository (current docs, library APIs, "
            "errors, recent events), use web.search to find sources and web.fetch to read the most "
            "relevant page — ground your answer in what you actually fetched rather than guessing."
        )
    base = (system_prompt or "").strip()
    return f"{base}\n\n{directive}" if base else directive


def provider_system_prompt(provider: Provider, system_prompt: str | None) -> str | None:
    del provider
    return system_prompt


def compose_provider_prompt(provider: Provider, prompt: str, system_prompt: str | None) -> str:
    del provider, system_prompt
    return prompt
