"""Deferred tool disclosure: which tools every turn carries, and which wait to be asked for.

Every Agents session used to offer all 26 manifest tools on every model call:
1.6K schema tokens for the nine coding tools and 6.2K for the other seventeen,
re-sent on each step of the tool loop. The pattern frontier harnesses settled on
(Claude Code's deferred tools, the Claude API's `defer_loading`) is a short
catalog plus one call that loads a tool for real. This module is CopeNet's
version: the always-loaded core below, a one-line-per-tool catalog in the
system prompt for the rest, and `tools.load` to bring one in. A loaded tool
stays loaded for the session (SessionStateRecord.loaded_tool_ids).

Chart-bound sessions are untouched: the chart lane scopes its own tool set.
"""

from __future__ import annotations

from typing import Iterable

from .contracts import ToolDescriptor

# The coding lane plus memory recall: what every ordinary turn needs without asking.
ALWAYS_LOADED_TOOL_IDS = frozenset(
    {
        "files.read",
        "files.edit",
        "files.write",
        "files.rg",
        "shell.exec",
        "plan.write",
        "artifact.read",
        "web.search",
        "web.fetch",
        "memory.read",
        "tools.load",
    }
)

CATALOG_LINE_CHARS = 150


def split_by_disclosure(
    tools: list[ToolDescriptor], *, loaded_tool_ids: Iterable[str] = ()
) -> tuple[list[ToolDescriptor], list[ToolDescriptor]]:
    """(available now, deferred): the core set plus anything already loaded, and the rest."""
    loaded = ALWAYS_LOADED_TOOL_IDS | {tool_id for tool_id in loaded_tool_ids if tool_id}
    available = [tool for tool in tools if tool.id in loaded]
    deferred = [tool for tool in tools if tool.id not in loaded]
    return available, deferred


def catalog_line(tool: ToolDescriptor) -> str:
    """One line of the catalog: the id and the first sentence of the description."""
    text = " ".join(str(tool.description or "").split())
    first = text.split(". ", 1)[0].rstrip(".")
    if len(first) > CATALOG_LINE_CHARS:
        first = first[: CATALOG_LINE_CHARS - 1].rstrip() + "…"
    return f"- {tool.id} — {first}"


def deferred_tool_overlay(deferred: list[ToolDescriptor]) -> str | None:
    """The system-prompt block that tells the model what it can ask for."""
    if not deferred:
        return None
    lines = "\n".join(catalog_line(tool) for tool in deferred)
    count = len(deferred)
    return (
        "<deferred_tools>\n"
        f"{count} more tool{'s are' if count != 1 else ' is'} available but not loaded. When a task needs one, call "
        "tools.load with its id(s); it is usable from your next step and stays loaded for this session. "
        "Do not call a deferred tool directly before loading it.\n"
        f"{lines}\n"
        "</deferred_tools>"
    )
