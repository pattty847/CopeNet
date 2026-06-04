"""Tool-approval park/decide flow: high-risk command pauses, operator decides."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions.session_store import SessionStore
from copenet.core.sessions.transcript_store import TranscriptStore


def _orch(tmp_path: Path) -> Orchestrator:
    return Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
    )


@pytest.mark.asyncio
async def test_await_approval_resolves_on_operator_decision(tmp_path: Path) -> None:
    orch = _orch(tmp_path)
    events: list[tuple[str, dict]] = []

    async def emit_event(name, payload):
        events.append((name, payload))

    abort = asyncio.Event()

    async def decide_soon(approval_id: str):
        await asyncio.sleep(0.02)
        orch.decide_approval(approval_id=approval_id, decision="approved", note="ok")

    # Kick the awaiter; the approvalId is fixed so we can decide on it.
    approval_id = "appr-test-1"
    decider = asyncio.create_task(decide_soon(approval_id))
    decision, note = await orch.await_tool_approval(
        session_key="s1",
        run_id="r1",
        approval_id=approval_id,
        request_payload={"toolId": "shell.exec", "description": "Run shell command: curl x", "target": "curl x", "payload": {"command": "curl x"}},
        emit_event=emit_event,
        abort_event=abort,
        timeout_sec=2.0,
    )
    await decider
    assert decision == "approved"
    assert note == "ok"
    # Emitted pending then resolved, with the ApprovalRequest shape.
    names = [name for name, _ in events]
    assert names == ["approval.pending", "approval.resolved"]
    pending = events[0][1]["approval"]
    assert pending["status"] == "pending"
    assert pending["actionClass"] == "process_execution"
    assert pending["proposedAction"]["payload"] == {"command": "curl x"}


@pytest.mark.asyncio
async def test_await_approval_aborts_when_run_aborts(tmp_path: Path) -> None:
    orch = _orch(tmp_path)

    async def emit_event(name, payload):
        return None

    abort = asyncio.Event()

    async def abort_soon():
        await asyncio.sleep(0.02)
        abort.set()

    aborter = asyncio.create_task(abort_soon())
    decision, _note = await orch.await_tool_approval(
        session_key="s1",
        run_id="r1",
        approval_id="appr-test-2",
        request_payload={"toolId": "shell.exec", "target": "sudo x", "payload": {"command": "sudo x"}},
        emit_event=emit_event,
        abort_event=abort,
        timeout_sec=2.0,
    )
    await aborter
    assert decision == "aborted"


def test_decide_unknown_approval_is_rejected(tmp_path: Path) -> None:
    orch = _orch(tmp_path)
    res = orch.decide_approval(approval_id="nope", decision="approved")
    assert res["ok"] is False
