"""Structured per-turn tool requests from the operator composer."""

from __future__ import annotations

from collections.abc import Iterable


def normalize_requested_tool_ids(
    requested_tool_ids: Iterable[str],
    *,
    registered_tool_ids: Iterable[str],
) -> tuple[str, ...]:
    """Keep unique, registered tool ids in the operator's requested order."""
    registered = set(registered_tool_ids)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_tool_id in requested_tool_ids:
        tool_id = str(raw_tool_id).strip()
        if not tool_id or tool_id in seen or tool_id not in registered:
            continue
        seen.add(tool_id)
        normalized.append(tool_id)
    return tuple(normalized)


def requested_tool_overlay(requested_tool_ids: Iterable[str]) -> str | None:
    """Build a turn-scoped instruction without altering visible user prose."""
    tool_ids = tuple(requested_tool_ids)
    if not tool_ids:
        return None
    tool_list = "\n".join(f"- `{tool_id}`" for tool_id in tool_ids)
    return (
        "<operator_requested_tools>\n"
        "The operator explicitly attached these tools to this turn:\n"
        f"{tool_list}\n"
        "Use each requested tool when it is applicable to fulfilling the user's request. "
        "Do not invent missing arguments or claim a tool ran when it did not.\n"
        "</operator_requested_tools>"
    )


def append_system_overlay(system_prompt: str | None, overlay: str | None) -> str | None:
    """Append one hidden turn overlay to the resolved system prompt."""
    if not overlay:
        return system_prompt
    if not system_prompt:
        return overlay
    return f"{system_prompt.rstrip()}\n\n{overlay}"
