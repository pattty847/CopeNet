"""files.read line-based mode — read by line range (the natural move after rg)."""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.tools import ToolExecutionRequest, ToolPolicy, ToolRegistry
from copenet.core.tools.contracts import ToolExecutionContext
from copenet.core.sessions.session_store import SessionStore
from copenet.core.sessions.transcript_store import TranscriptStore


def _ctx(tmp_path: Path, *, file_output_limit: int = 12000) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="s",
        provider_name="t",
        model="t",
        session_store=SessionStore(path=tmp_path / "i.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        providers={},
        policy=ToolPolicy(allowed_categories={"repo-read"}, file_output_limit=file_output_limit),
    )


def _write(tmp_path: Path, name: str, n_lines: int) -> None:
    (tmp_path / name).write_text("\n".join(f"line{i}" for i in range(1, n_lines + 1)), encoding="utf-8")


@pytest.mark.asyncio
async def test_read_exact_line_range(tmp_path: Path) -> None:
    _write(tmp_path, "f.py", 20)
    res = await ToolRegistry().execute(
        ToolExecutionRequest("files.read", {"path": "f.py", "start_line": 3, "end_line": 5}), _ctx(tmp_path)
    )
    assert res.ok is True
    assert res.output["content"] == "line3\nline4\nline5"
    assert res.output["startLine"] == 3 and res.output["endLine"] == 5
    assert res.output["totalLines"] == 20
    assert res.output["truncated"] is False


@pytest.mark.asyncio
async def test_start_line_only_reads_to_eof(tmp_path: Path) -> None:
    _write(tmp_path, "f.py", 10)
    res = await ToolRegistry().execute(
        ToolExecutionRequest("files.read", {"path": "f.py", "start_line": 8}), _ctx(tmp_path)
    )
    assert res.output["content"] == "line8\nline9\nline10"
    assert res.output["endLine"] == 10


@pytest.mark.asyncio
async def test_end_line_beyond_eof_clamps(tmp_path: Path) -> None:
    _write(tmp_path, "f.py", 5)
    res = await ToolRegistry().execute(
        ToolExecutionRequest("files.read", {"path": "f.py", "start_line": 4, "end_line": 999}), _ctx(tmp_path)
    )
    assert res.output["endLine"] == 5
    assert res.output["content"].endswith("line5")


@pytest.mark.asyncio
async def test_line_read_truncates_at_char_cap_and_tells_model(tmp_path: Path) -> None:
    # 200 lines; a tiny char cap forces truncation mid-range with a clear continuation.
    _write(tmp_path, "big.py", 200)
    res = await ToolRegistry().execute(
        ToolExecutionRequest("files.read", {"path": "big.py", "start_line": 1, "end_line": 200}),
        _ctx(tmp_path, file_output_limit=40),  # ~ a handful of "lineN\n"
    )
    assert res.output["truncated"] is True
    assert res.output["endLine"] < 200
    assert "nextStartLine" in res.output
    assert res.output["nextStartLine"] == res.output["endLine"] + 1
    assert "Continue with start_line=" in res.output["content"]


@pytest.mark.asyncio
async def test_char_mode_still_works_and_reports_total_lines(tmp_path: Path) -> None:
    _write(tmp_path, "f.py", 12)
    res = await ToolRegistry().execute(
        ToolExecutionRequest("files.read", {"path": "f.py", "offset": 0, "limit": 11}), _ctx(tmp_path)
    )
    # char-based slice unchanged; now also reports totalLines for line-aware nav
    assert res.output["content"].startswith("line1")
    assert res.output["totalLines"] == 12
