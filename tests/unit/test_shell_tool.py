from pathlib import Path

import pytest

from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolPolicy, ToolRegistry, policy_for_task_mode


def _context(tmp_path: Path) -> ToolExecutionContext:
    return _context_with_policy(tmp_path, ToolPolicy(shell_allowlist=("grep", "pwd")))


def _context_with_policy(tmp_path: Path, policy: ToolPolicy) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="alpha",
        provider_name="test",
        model=None,
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={},
        policy=policy,
        trace=None,
    )


@pytest.mark.asyncio
async def test_shell_exec_returns_stdout_to_prompt_and_preview(tmp_path: Path) -> None:
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "pwd"}),
        _context(tmp_path),
    )

    assert result.ok is True
    assert result.output["exitCode"] == 0
    assert result.output["stdout"].strip() == str(tmp_path)
    assert str(tmp_path) in result.to_prompt_payload()
    assert result.to_event_payload()["preview"]["preview"].endswith(str(tmp_path))


@pytest.mark.asyncio
async def test_shell_exec_failed_command_preserves_stdout_stderr(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "grep missing README.md"}),
        _context(tmp_path),
    )

    assert result.ok is False
    assert result.output["exitCode"] == 1
    assert result.output["stdout"] == ""
    assert "exit 1" in result.error
    assert '"exitCode": 1' in result.to_prompt_payload()


@pytest.mark.asyncio
async def test_shell_exec_blocks_chained_shell_syntax(tmp_path: Path) -> None:
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "pwd && git status --short"}),
        _context(tmp_path),
    )

    assert result.ok is False
    assert result.output["policyDecision"] == "unsafe_unknown"
    assert "one allowlisted command only" in result.error


@pytest.mark.asyncio
async def test_full_access_shell_exec_allows_shell_syntax(tmp_path: Path) -> None:
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "printf hi | tr a-z A-Z"}),
        _context_with_policy(tmp_path, policy_for_task_mode("full-access")),
    )

    assert result.ok is True
    assert result.output["exitCode"] == 0
    assert result.output["stdout"] == "HI"
    assert result.output["policySummary"] == "Full-access shell command executed with the current user's permissions."


@pytest.mark.asyncio
async def test_full_access_shell_exec_requires_approval_for_high_risk_commands(tmp_path: Path) -> None:
    registry = ToolRegistry()
    result = await registry.execute(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "sudo reboot"}),
        _context_with_policy(tmp_path, policy_for_task_mode("full-access")),
    )

    assert result.ok is False
    assert result.output["policyDecision"] == "approval_required"
    assert "approval required" in result.error
