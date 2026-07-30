"""Regression tests for file tools and opt-in memory extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from copenet.core._config import (
    auto_memory_extraction_enabled,
)
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolPolicy
from copenet.core.tools.handlers.files import FILE_READ_ABSOLUTE_MAX, read_file, ripgrep_files


def _make_context(workdir: Path, *, policy: ToolPolicy | None = None) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=workdir,
        session_workspace_root=workdir,
        session_key="test",
        provider_name="test",
        model=None,
        session_store=None,  # type: ignore[arg-type]
        transcript_store=None,  # type: ignore[arg-type]
        providers={},
        policy=policy or ToolPolicy(),
        available_tools=[],
        memory_service=None,
        workspace_intel_service=None,
        artifact_store=None,
        task_prompt_id=None,
        run_id="test-run",
        trace=None,
    )


def test_auto_extraction_is_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Memory auto-extraction stays disabled without explicit opt-in."""
    monkeypatch.delenv("COPNET_AUTO_MEMORY_EXTRACTION", raising=False)
    assert auto_memory_extraction_enabled() is False


def test_auto_extraction_respects_env_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPNET_AUTO_MEMORY_EXTRACTION", "1")
    assert auto_memory_extraction_enabled() is True


@pytest.mark.asyncio
async def test_files_read_honors_explicit_limit_above_policy_default(tmp_path: Path) -> None:
    """An explicit safe limit is not silently clamped to the policy default."""
    big = "x" * 50_000
    target = tmp_path / "big.txt"
    target.write_text(big, encoding="utf-8")
    context = _make_context(tmp_path, policy=ToolPolicy(file_output_limit=12_000))

    result = await read_file(
        ToolExecutionRequest(tool_id="files.read", arguments={"path": "big.txt", "limit": 50_000}),
        context,
    )
    assert result.ok
    content = result.output["content"]
    # The first 50k chars should be all there; truncated text isn't appended.
    assert "[Read truncated" not in content
    assert len(content) >= 50_000


@pytest.mark.asyncio
async def test_files_read_default_limit_emits_continuation_hint(tmp_path: Path) -> None:
    """The default page explains how to continue after truncation."""
    big = "y" * 30_000
    target = tmp_path / "big.txt"
    target.write_text(big, encoding="utf-8")
    context = _make_context(tmp_path, policy=ToolPolicy(file_output_limit=12_000))

    result = await read_file(
        ToolExecutionRequest(tool_id="files.read", arguments={"path": "big.txt"}),
        context,
    )
    assert result.ok
    assert result.output["truncated"] is True
    content = result.output["content"]
    assert "[Read truncated" in content
    assert "Use offset=" in content


@pytest.mark.asyncio
async def test_files_read_absolute_max_safety_guard(tmp_path: Path) -> None:
    """Limits over the absolute maximum are clamped to the safety guard."""
    target = tmp_path / "big.txt"
    target.write_text("z" * 1000, encoding="utf-8")
    context = _make_context(tmp_path)
    result = await read_file(
        ToolExecutionRequest(
            tool_id="files.read",
            arguments={"path": "big.txt", "limit": FILE_READ_ABSOLUTE_MAX + 1_000_000},
        ),
        context,
    )
    assert result.ok
    assert result.output["limit"] == FILE_READ_ABSOLUTE_MAX


@pytest.mark.asyncio
async def test_files_rg_pagination_and_hint(tmp_path: Path) -> None:
    """files.rg paginates and explains how to request the next page."""
    # 30 files each containing the pattern once.
    for i in range(30):
        (tmp_path / f"file_{i:02}.txt").write_text(f"line above\nNEEDLE-{i}\nline below\n", encoding="utf-8")
    context = _make_context(tmp_path)

    result = await ripgrep_files(
        ToolExecutionRequest(
            tool_id="files.rg",
            arguments={"pattern": "NEEDLE", "limit": 10, "offset": 0},
        ),
        context,
    )
    if not result.ok:
        pytest.skip(f"ripgrep not available in environment: {result.error}")
    assert result.output["totalMatches"] >= 30
    assert len(result.output["matches"]) == 10
    assert result.output["truncated"] is True
    assert result.output["nextOffset"] == 10
    # Continuation hint surfaces in the result summary.
    assert "offset=10" in result.summary
