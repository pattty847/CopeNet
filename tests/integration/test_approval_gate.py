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
from copenet.core.permissions.store import PermissionStore
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


def _full_access_context(
    tmp_path: Path, *, permission_store: PermissionStore | None = None, ephemeral: dict | None = None
) -> ToolExecutionContext:
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
        permission_store=permission_store,
        ephemeral=ephemeral if ephemeral is not None else {},
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


@pytest.mark.asyncio
async def test_approving_a_non_shell_write_does_not_grant_standing_shell_authority(
    tmp_path: Path,
) -> None:
    # Confirmed audit finding (C-A-009): "always allow" on a non-shell tool used to
    # persist the tool's TARGET (e.g. a file path) into the global, cross-session
    # shell.exec permission store, because the fallback `command or target` picked
    # up the file path when the approval came from a non-shell gate (e.g. the
    # Barricade's tainted-write approval). A later, unrelated run could then run
    # that path as a standing-approved shell command with no further prompt.
    orch = _orch(tmp_path)
    abort = asyncio.Event()
    permission_store = PermissionStore(tmp_path / "permissions.json")

    async def emit_event(name, payload):
        if name == "approval.pending":
            approval_id = payload["approval"]["approvalId"]
            orch.decide_approval(approval_id=approval_id, decision="approved_always")

    gated = _make_approval_gated_executor(
        ToolRegistry().execute,
        orchestrator=orch,
        emit_event=emit_event,
        session_key="appr-sess",
        run_id="run-appr",
        abort_event=abort,
    )

    context = _full_access_context(
        tmp_path,
        permission_store=permission_store,
        ephemeral={"security": _tainted_security_state()},
    )

    write_path = str(tmp_path / "script.sh")
    result = await gated(
        ToolExecutionRequest(tool_id="files.write", arguments={"path": write_path, "content": "x"}),
        context,
    )

    assert result.ok is True
    # The write's target must never appear as an approved shell command.
    assert permission_store.is_allowed(write_path) is False
    assert permission_store.is_allowed("script.sh") is False


def _tainted_security_state():
    from copenet.core.tools.barricade import RunSecurityState

    state = RunSecurityState()
    state.untrusted_context = True
    state.untrusted_sources = ["web.search"]
    return state
