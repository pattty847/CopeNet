"""plan.write — the model's task checklist tool."""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.tools import ToolExecutionRequest, ToolPolicy, ToolRegistry
from copenet.core.tools.contracts import ToolExecutionContext
from copenet.core.sessions.session_store import SessionStore
from copenet.core.sessions.transcript_store import TranscriptStore


def _ctx(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="s",
        provider_name="t",
        model="t",
        session_store=SessionStore(path=tmp_path / "i.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        providers={},
        policy=ToolPolicy(allowed_categories={"context"}),
    )


@pytest.mark.asyncio
async def test_plan_write_records_items_and_summarizes(tmp_path: Path) -> None:
    result = await ToolRegistry().execute(
        ToolExecutionRequest(
            tool_id="plan.write",
            arguments={
                "items": [
                    {"content": "Read the code", "status": "completed"},
                    {"content": "Make the change", "status": "in_progress"},
                    {"content": "Run tests", "status": "pending"},
                ]
            },
        ),
        _ctx(tmp_path),
    )
    assert result.ok is True
    assert result.output["total"] == 3
    assert result.output["completed"] == 1
    assert "1/3" in result.summary
    assert "Make the change" in result.summary  # surfaces the in_progress item


@pytest.mark.asyncio
async def test_plan_write_normalizes_bad_status_and_drops_empty(tmp_path: Path) -> None:
    result = await ToolRegistry().execute(
        ToolExecutionRequest(
            tool_id="plan.write",
            arguments={"items": [{"content": "ok", "status": "weird"}, {"content": "  ", "status": "pending"}]},
        ),
        _ctx(tmp_path),
    )
    assert result.ok is True
    assert result.output["items"] == [{"content": "ok", "status": "pending"}]  # bad status -> pending, empty dropped


@pytest.mark.asyncio
async def test_plan_write_requires_items(tmp_path: Path) -> None:
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="plan.write", arguments={"items": []}),
        _ctx(tmp_path),
    )
    # empty list -> a clear failure, not a crash
    assert result.ok is False


@pytest.mark.asyncio
async def test_plan_write_emits_plan_preview(tmp_path: Path) -> None:
    result = await ToolRegistry().execute(
        ToolExecutionRequest(
            tool_id="plan.write",
            arguments={"items": [{"content": "step", "status": "pending"}]},
        ),
        _ctx(tmp_path),
    )
    preview = result.to_event_payload().get("preview")
    assert preview == {"type": "plan", "items": [{"content": "step", "status": "pending"}]}
