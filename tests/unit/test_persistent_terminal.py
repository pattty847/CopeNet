from pathlib import Path

import pytest

from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.orchestrator.run_harness import _close_terminal_when_stream_ends
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolRegistry, policy_for_task_mode
from copenet.core.tools.handlers.terminal import close_terminal_for_run


def _context(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="terminal-test",
        provider_name="test",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={},
        policy=policy_for_task_mode("full-access"),
    )


@pytest.mark.asyncio
async def test_terminal_keeps_directory_and_environment_until_closed(tmp_path: Path) -> None:
    work = tmp_path / "child"
    work.mkdir()
    context = _context(tmp_path)
    registry = ToolRegistry()

    started = await registry.execute(ToolExecutionRequest("terminal.start"), context)
    changed = await registry.execute(ToolExecutionRequest("terminal.exec", {"command": "cd child; export COPENET_TERMINAL_TEST=ready"}), context)
    observed = await registry.execute(ToolExecutionRequest("terminal.exec", {"command": "printf '%s:%s' \"$PWD\" \"$COPENET_TERMINAL_TEST\""}), context)

    assert started.ok is True
    assert changed.ok is True
    assert observed.ok is True
    assert f"{work}:ready" in observed.output["output"]

    closed = await registry.execute(ToolExecutionRequest("terminal.close"), context)
    assert closed.ok is True
    inactive = await registry.execute(ToolExecutionRequest("terminal.exec", {"command": "pwd"}), context)
    assert inactive.ok is False


@pytest.mark.asyncio
async def test_terminal_runtime_cleanup_closes_an_unclosed_session(tmp_path: Path) -> None:
    context = _context(tmp_path)
    registry = ToolRegistry()
    await registry.execute(ToolExecutionRequest("terminal.start"), context)
    terminal = context.ephemeral["persistent_terminal"]

    await close_terminal_for_run(context)

    assert terminal.active is False
    assert "persistent_terminal" not in context.ephemeral


@pytest.mark.asyncio
async def test_harness_stream_cleanup_closes_an_unclosed_session(tmp_path: Path) -> None:
    context = _context(tmp_path)
    registry = ToolRegistry()
    await registry.execute(ToolExecutionRequest("terminal.start"), context)
    terminal = context.ephemeral["persistent_terminal"]

    async def events():
        yield {"kind": "final"}

    async for _event in _close_terminal_when_stream_ends(events(), context):
        pass

    assert terminal.active is False
    assert "persistent_terminal" not in context.ephemeral


@pytest.mark.asyncio
async def test_terminal_exec_honors_high_risk_approval_gate(tmp_path: Path) -> None:
    context = _context(tmp_path)
    registry = ToolRegistry()
    await registry.execute(ToolExecutionRequest("terminal.start"), context)

    result = await registry.execute(ToolExecutionRequest("terminal.exec", {"command": "sudo reboot"}), context)

    assert result.ok is False
    assert result.output["policyDecision"] == "approval_required"
    await close_terminal_for_run(context)
