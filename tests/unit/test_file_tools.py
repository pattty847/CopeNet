from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolPolicy, ToolRegistry


def _tool_context(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_key="alpha",
        provider_name="prompted",
        model="test-model",
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={},
        policy=ToolPolicy(),
    )


@pytest.mark.asyncio
async def test_files_rg_returns_bounded_matches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry = ToolRegistry()

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                '{"type":"match","data":{"path":{"text":"src/app.py"},"lines":{"text":"needle appears here\\n"},"line_number":12,"submatches":[{"match":{"text":"needle"},"start":4,"end":10}]}}\n'
                '{"type":"match","data":{"path":{"text":"README.md"},"lines":{"text":"needle again\\n"},"line_number":3,"submatches":[{"match":{"text":"needle"},"start":0,"end":6}]}}\n'
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.rg", arguments={"pattern": "needle", "path": "."}),
        _tool_context(tmp_path),
    )

    assert result.ok is True
    assert result.summary == "Found 2 matches for pattern via ripgrep."
    assert result.output["matches"] == [
        {"path": "src/app.py", "line": 12, "column": 5, "text": "needle appears here"},
        {"path": "README.md", "line": 3, "column": 1, "text": "needle again"},
    ]


@pytest.mark.asyncio
async def test_files_rg_fails_clearly_when_rg_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry = ToolRegistry()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("rg")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.rg", arguments={"pattern": "needle", "path": "."}),
        _tool_context(tmp_path),
    )

    assert result.ok is False
    assert result.error == "ripgrep (rg) is not installed or not available on PATH"
