"""End-to-end approval gate: a high-risk shell command pauses, then runs on approve.

Exercises the real pieces together — the executor wrapper
(_make_approval_gated_executor), the shell handler's approval gate + pre-approval
bypass, and the orchestrator await/decide registry — without the live provider
loop or a browser.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from copenet.core.orchestrator import Orchestrator
from copenet.core.orchestrator.runtime import _make_approval_gated_executor
from copenet.core.sessions.session_store import SessionStore
from copenet.core.sessions.transcript_store import TranscriptStore
from copenet.core.tools import ToolExecutionRequest, ToolPolicy, ToolRegistry, policy_for_task_mode
from copenet.core.tools.contracts import ToolExecutionContext


def _orch(tmp_path: Path) -> Orchestrator:
    return Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
    )


def _full_access_context(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="appr-sess",
        provider_name="test",
        model="test",
        session_store=SessionStore(path=tmp_path / "ix.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        providers={},
        policy=policy_for_task_mode("full-access"),
        run_id="run-appr",
    )


@pytest.mark.asyncio
async def test_high_risk_command_pauses_then_runs_on_approve(tmp_path: Path) -> None:
    orch = _orch(tmp_path)
    abort = asyncio.Event()
    pending_ids: list[str] = []

    async def emit_event(name, payload):
        if name == "approval.pending":
            approval_id = payload["approval"]["approvalId"]
            pending_ids.append(approval_id)
            # Operator approves as soon as the request lands.
            await asyncio.sleep(0)
            orch.decide_approval(approval_id=approval_id, decision="approved")

    gated = _make_approval_gated_executor(
        ToolRegistry().execute,
        orchestrator=orch,
        emit_event=emit_event,
        session_key="appr-sess",
        run_id="run-appr",
        abort_event=abort,
    )

    # `systemctl` matches a high-risk pattern. On approve it actually runs
    # (here it just fails to exist on macOS) — the point is it got PAST the gate.
    result = await gated(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "systemctl --version"}),
        _full_access_context(tmp_path),
    )

    assert len(pending_ids) == 1  # paused exactly once
    output = result.output if isinstance(result.output, dict) else {}
    # After approval the result is a normal shell exec, NOT the approval gate.
    assert output.get("policyDecision") != "approval_required"
    assert "exitCode" in output  # it executed


@pytest.mark.asyncio
async def test_high_risk_command_stays_blocked_on_reject(tmp_path: Path) -> None:
    orch = _orch(tmp_path)
    abort = asyncio.Event()

    async def emit_event(name, payload):
        if name == "approval.pending":
            approval_id = payload["approval"]["approvalId"]
            orch.decide_approval(approval_id=approval_id, decision="rejected")

    gated = _make_approval_gated_executor(
        ToolRegistry().execute,
        orchestrator=orch,
        emit_event=emit_event,
        session_key="appr-sess",
        run_id="run-appr",
        abort_event=abort,
    )

    result = await gated(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "systemctl stop everything"}),
        _full_access_context(tmp_path),
    )
    output = result.output if isinstance(result.output, dict) else {}
    # Rejected → the model is told a human said no (so it adapts instead of
    # retrying), and the command never ran.
    assert output.get("policyDecision") == "rejected_by_operator"
    assert output.get("operatorDecision") == "rejected"
    assert "exitCode" not in output


@pytest.mark.asyncio
async def test_no_emit_event_falls_back_to_blocked(tmp_path: Path) -> None:
    # CLI path (no side channel) — no operator to ask, so the blocked result
    # is returned as before instead of hanging.
    orch = _orch(tmp_path)
    gated = _make_approval_gated_executor(
        ToolRegistry().execute,
        orchestrator=orch,
        emit_event=None,
        session_key="appr-sess",
        run_id="run-appr",
        abort_event=asyncio.Event(),
    )
    result = await gated(
        ToolExecutionRequest(tool_id="shell.exec", arguments={"command": "sudo rm something"}),
        _full_access_context(tmp_path),
    )
    output = result.output if isinstance(result.output, dict) else {}
    assert output.get("policyDecision") == "approval_required"
