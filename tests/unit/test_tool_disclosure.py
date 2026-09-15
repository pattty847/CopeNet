"""Deferred tool disclosure: the core set is offered, the rest is a catalog until tools.load."""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.sessions.state_store import SessionStateStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolPolicy, ToolRegistry
from copenet.core.tools.disclosure import ALWAYS_LOADED_TOOL_IDS, deferred_tool_overlay, split_by_disclosure


def _context(tmp_path: Path, *, deferred: dict, available: list, session_key: str = "s") -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key=session_key,
        provider_name="scripted",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={},
        policy=ToolPolicy(),
        available_tools=available,
        session_state_store=SessionStateStore(root_dir=tmp_path / "state"),
        ephemeral={"deferred_tools": deferred, "loaded_tool_ids": []},
    )


def test_manifest_splits_into_the_core_set_and_a_deferred_catalog() -> None:
    tools = ToolRegistry().list_tools()
    available, deferred = split_by_disclosure(tools)
    assert {tool.id for tool in available} == ALWAYS_LOADED_TOOL_IDS & {tool.id for tool in tools}
    assert "tools.load" in {tool.id for tool in available}
    deferred_ids = {tool.id for tool in deferred}
    assert {"market.ticker", "market.chart.apply", "memory.write", "persona.author", "user.remember"} <= deferred_ids
    assert not deferred_ids & ALWAYS_LOADED_TOOL_IDS
    # a session that already loaded a tool starts with it available
    available2, deferred2 = split_by_disclosure(tools, loaded_tool_ids=["market.ticker"])
    assert "market.ticker" in {tool.id for tool in available2} and "market.ticker" not in {tool.id for tool in deferred2}


def test_overlay_is_one_line_per_tool_and_names_the_load_call() -> None:
    _, deferred = split_by_disclosure(ToolRegistry().list_tools())
    overlay = deferred_tool_overlay(deferred)
    assert overlay.startswith("<deferred_tools>") and overlay.endswith("</deferred_tools>")
    assert "call tools.load" in overlay
    lines = [line for line in overlay.splitlines() if line.startswith("- ")]
    assert len(lines) == len(deferred)
    assert all(len(line) < 200 for line in lines)
    assert any(line.startswith("- market.ticker — ") for line in lines)
    assert deferred_tool_overlay([]) is None


@pytest.mark.asyncio
async def test_tools_load_brings_a_deferred_tool_in_and_persists_it_for_the_session(tmp_path: Path) -> None:
    registry = ToolRegistry()
    available, deferred = split_by_disclosure(registry.list_tools())
    context = _context(tmp_path, deferred={tool.id: tool for tool in deferred}, available=available)

    result = await registry.execute(ToolExecutionRequest("tools.load", {"tool_ids": ["market.ticker", "files.read", "nope.tool"]}), context)
    assert result.ok, result.error
    assert result.output == {"loaded": ["market.ticker"], "alreadyAvailable": ["files.read"], "unknown": ["nope.tool"]}
    assert "available from your next step" in result.summary
    assert context.ephemeral["loaded_tool_ids"] == ["market.ticker"]
    assert context.session_state_store.get("s").loaded_tool_ids == ["market.ticker"]

    again = await registry.execute(ToolExecutionRequest("tools.load", {"tool_ids": ["market.ticker"]}), context)
    assert again.ok and again.output["loaded"] == [] and again.output["alreadyAvailable"] == ["market.ticker"]

    unknown = await registry.execute(ToolExecutionRequest("tools.load", {"tool_ids": ["nope.tool"]}), context)
    assert unknown.ok is False and "Loadable ids:" in str(unknown.error) and "market.ticker" in str(unknown.error)
