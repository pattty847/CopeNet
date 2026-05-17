from pathlib import Path

import pytest

from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolRegistry, policy_for_task_mode


def _context(tmp_path: Path, *, task_mode: str | None = None) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="alpha",
        provider_name="test",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={},
        policy=policy_for_task_mode(task_mode),
        trace=None,
    )


@pytest.mark.asyncio
async def test_context_prepare_reports_default_permissions(tmp_path: Path) -> None:
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="context.prepare", arguments={}),
        _context(tmp_path),
    )

    permissions = result.output["runtime"]["permissions"]
    assert permissions["repoWriteEnabled"] is False
    assert permissions["shell"]["unrestricted"] is False
    assert "repo-write" not in permissions["allowedCategories"]


@pytest.mark.asyncio
async def test_context_prepare_reports_full_access_permissions(tmp_path: Path) -> None:
    result = await ToolRegistry().execute(
        ToolExecutionRequest(tool_id="context.prepare", arguments={}),
        _context(tmp_path, task_mode="full-access"),
    )

    permissions = result.output["runtime"]["permissions"]
    assert permissions["repoWriteEnabled"] is True
    assert permissions["shell"]["unrestricted"] is True
    assert "repo-write" in permissions["allowedCategories"]
    assert "git reset" in permissions["shell"]["approvalPatterns"]
