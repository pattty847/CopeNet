"""Estimating and bounding the provider-bound input view.

One owner for "how big is this request" and "what do we drop". Both the
orchestrator (before a turn starts) and the tool loops (as a turn grows) use
these, so a long agentic turn cannot walk off the context window after the
initial trim said it was fine.

Durable transcript storage is never touched — these operate only on the outbound
message view.
"""

from __future__ import annotations

import json
from typing import Any

# A base64 image costs the model far fewer tokens than its encoded length, but it
# is emphatically not free. Charging encoded_len/IMAGE_CHARS_PER_TOKEN_DIVISOR keeps
# images visible to the budget without pretending we know the tiling cost. It is a
# deliberate over-estimate: overflow is expensive, over-trimming is merely lossy.
IMAGE_CHARS_PER_TOKEN_DIVISOR = 40


def estimate_input_tokens(messages: list[dict[str, Any]]) -> int:
    """Rough char/4 token estimate over the input array."""
    return max(sum(item_estimated_chars(item) for item in messages) // 4, 0)


def estimate_request_tokens(
    messages: list[dict[str, Any]],
    *,
    instructions: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> int:
    """Estimate the complete provider request, not only its message bodies."""
    structural_chars = 64 * len(messages)
    if instructions:
        structural_chars += len(instructions)
    if tools:
        structural_chars += len(json.dumps(tools, ensure_ascii=False, separators=(",", ":")))
    return estimate_input_tokens(messages) + ((structural_chars + 3) // 4)


def item_estimated_chars(item: dict[str, Any]) -> int:
    """Charge every item shape, including the ones we do not model yet."""
    item_type = item.get("type")
    if item_type == "function_call":
        return len(str(item.get("name") or "")) + len(str(item.get("arguments") or ""))
    if item_type == "function_call_output":
        return len(str(item.get("output") or ""))
    if item_type == "reasoning":
        # Encrypted reasoning is opaque but still occupies the window.
        return len(str(item.get("encrypted_content") or "")) + sum(
            len(str(entry.get("text") or ""))
            for entry in (item.get("summary") or [])
            if isinstance(entry, dict)
        )
    content = item.get("content")
    if isinstance(content, list):
        return sum(_content_part_chars(part) for part in content if isinstance(part, dict))
    if content is not None:
        return len(str(content))
    # An unmodelled shape (compaction, phase, a future output type) must cost
    # something, or the budget silently under-counts as the provider API evolves.
    return len(json.dumps(item, ensure_ascii=False))


def _content_part_chars(part: dict[str, Any]) -> int:
    """Charge every content part, not just the ones carrying `text`.

    `input_image` parts hold their base64 payload under `image_url`. Counting only
    `text` made a multi-megabyte vision conversation estimate as a handful of
    tokens, so the budget never fired on the payloads most likely to overflow.
    """
    text = part.get("text")
    if isinstance(text, str):
        return len(text)
    image_url = part.get("image_url")
    if isinstance(image_url, str):
        return max(len(image_url) // IMAGE_CHARS_PER_TOKEN_DIVISOR, 1)
    if isinstance(image_url, dict):  # Chat-Completions-style {"url": ...}
        return max(len(str(image_url.get("url") or "")) // IMAGE_CHARS_PER_TOKEN_DIVISOR, 1)
    return len(json.dumps(part, ensure_ascii=False))


def trim_messages_to_token_budget(
    messages: list[dict[str, Any]],
    *,
    max_context_tokens: int,
) -> list[dict[str, Any]]:
    """Keep the newest complete user turns within an approximate token budget.

    Tool calls and results stay together. Old turns are removed first; if the live
    turn grew through tools, its newest complete exchanges are retained. The live
    user item itself is never truncated and is rejected if it cannot fit.
    """
    if max_context_tokens <= 0 or estimate_input_tokens(messages) <= max_context_tokens:
        return list(messages)
    groups = group_by_user_turn(messages)
    if not groups:
        return list(messages)

    live = _trim_live_turn(groups[-1], max_context_tokens)
    selected = [live]
    remaining = max_context_tokens - estimate_input_tokens(live)
    for group in reversed(groups[:-1]):
        group_tokens = estimate_input_tokens(group)
        if group_tokens > remaining:
            break
        selected.append(group)
        remaining -= group_tokens
    selected.reverse()
    return [item for group in selected for item in group]


def trim_messages_to_request_budget(
    messages: list[dict[str, Any]],
    *,
    max_input_tokens: int,
    instructions: str | None = None,
    tools: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Bound messages after charging fixed instructions and tool schemas."""
    fixed = estimate_request_tokens([], instructions=instructions, tools=tools)
    message_budget = max_input_tokens - fixed
    if message_budget <= 0:
        raise ValueError("Provider instructions and tool schemas exceed the input budget")
    bounded = trim_messages_to_token_budget(messages, max_context_tokens=message_budget)
    if estimate_request_tokens(bounded, instructions=instructions, tools=tools) > max_input_tokens:
        raise ValueError("Current turn exceeds the provider input budget")
    return bounded


def _trim_live_turn(group: list[dict[str, Any]], budget: int) -> list[dict[str, Any]]:
    if not group:
        return []
    user = group[0]
    user_cost = estimate_input_tokens([user])
    if user_cost > budget:
        raise ValueError("Current user turn exceeds the provider input budget")
    if estimate_input_tokens(group) <= budget:
        return list(group)

    outputs = {
        str(item.get("call_id")): index
        for index, item in enumerate(group)
        if item.get("type") == "function_call_output" and item.get("call_id")
    }
    consumed = {0}
    chunks: list[list[tuple[int, dict[str, Any]]]] = []
    for index, item in enumerate(group[1:], start=1):
        if index in consumed or item.get("type") == "function_call_output":
            continue
        if item.get("type") == "function_call" and item.get("call_id"):
            output_index = outputs.get(str(item["call_id"]))
            if output_index is not None:
                consumed.add(output_index)
                chunks.append([(index, item), (output_index, group[output_index])])
                continue
        chunks.append([(index, item)])

    selected: list[list[tuple[int, dict[str, Any]]]] = []
    remaining = budget - user_cost
    for chunk in reversed(chunks):
        chunk_items = [item for _, item in chunk]
        cost = estimate_input_tokens(chunk_items)
        if cost > remaining:
            break
        selected.append(chunk)
        remaining -= cost
    flattened = [pair for chunk in reversed(selected) for pair in chunk]
    return [user, *(item for _, item in sorted(flattened, key=lambda pair: pair[0]))]


def group_by_user_turn(messages: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split an input array at `role: "user"` boundaries.

    Everything a turn produced — assistant text, function_call, function_call_output,
    reasoning — travels with the user message that caused it, so trimming can never
    orphan a tool call from its result.
    """
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for item in messages:
        if item.get("role") == "user" and current:
            groups.append(current)
            current = []
        current.append(item)
    if current:
        groups.append(current)
    return groups
