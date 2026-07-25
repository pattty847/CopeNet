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

    Tool calls and results stay together because selection happens at user-turn
    boundaries. The live/current turn is always retained even if it alone exceeds
    the budget — a request the model cannot see is worse than one that is too big.
    """
    if max_context_tokens <= 0 or estimate_input_tokens(messages) <= max_context_tokens:
        return list(messages)
    groups = group_by_user_turn(messages)
    if not groups:
        return list(messages)

    selected = [groups[-1]]
    remaining = max_context_tokens - estimate_input_tokens(groups[-1])
    for group in reversed(groups[:-1]):
        group_tokens = estimate_input_tokens(group)
        if group_tokens > remaining:
            break
        selected.append(group)
        remaining -= group_tokens
    selected.reverse()
    return [item for group in selected for item in group]


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
