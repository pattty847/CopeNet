"""Execution outcomes survive notification failures and interruption."""

import asyncio
from dataclasses import replace

import pytest

from test_resolved_model import ResolvingProvider, _orchestrator
from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.providers import ProviderEvent


async def noop(payload):
    pass


def request():
    return ChatSendRequest(
        session_key="finalization",
        message="Hello",
        provider="fake",
        model="fake-model",
        idempotency_key="finalization-run",
    )


@pytest.mark.parametrize("failed_state", ["delta", "final", "all"])
async def test_delivery_failure_does_not_change_execution_outcome(tmp_path, failed_state):
    orch = _orchestrator(tmp_path, ResolvingProvider())

    async def emit(payload):
        if failed_state == "all" or payload["state"] == failed_state:
            raise RuntimeError("synthetic sink failure")

    result = await orch.send_chat(request(), emit=emit)
    assert result["status"] == "ok"
    records = orch._run_store.list_for_session(request().session_key)
    assert len(records) == 1 and records[0].status == "ok"
    retry = await orch.send_chat(request(), emit=noop)
    assert retry["cached"] and retry["result"]["state"] == "final"
    assert len(orch.history(session_key=request().session_key)) == 2
    assert not orch._active_run_by_session


class FailingProvider(ResolvingProvider):
    async def run(self, **kwargs):
        yield ProviderEvent(kind="delta", text="Partial answer")
        raise RuntimeError("synthetic provider failure")


async def test_provider_failure_persists_partial_activity_even_if_error_delivery_fails(tmp_path):
    orch = _orchestrator(tmp_path, FailingProvider())

    async def emit(payload):
        raise RuntimeError("synthetic sink failure")

    result = await orch.send_chat(request(), emit=emit)
    assert result["status"] == "error"
    records = orch._run_store.list_for_session(request().session_key)
    assert len(records) == 1 and records[0].error == "synthetic provider failure"
    assistant = orch.history(session_key=request().session_key)[-1]
    assert assistant["content"] == "Partial answer"
    assert assistant["state"] == "error"


async def test_task_cancellation_persists_interrupted_activity_and_releases_session(tmp_path):
    orch = _orchestrator(tmp_path, ResolvingProvider())

    async def cancel(payload):
        if payload["state"] == "delta":
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await orch.send_chat(request(), emit=cancel)
    records = orch._run_store.list_for_session(request().session_key)
    assert len(records) == 1 and records[0].status == "interrupted"
    assert orch.history(session_key=request().session_key)[-1]["state"] == "interrupted"
    assert not orch._active_run_by_session and not orch._active_abort_by_run


async def test_finalized_outputs_use_answering_model_without_mutating_session_choice(tmp_path):
    orch = _orchestrator(tmp_path, ResolvingProvider())
    frames = []

    async def emit(payload):
        frames.append(payload)

    await orch.send_chat(request(), emit=emit)
    assert frames[-1]["model"] == "fake-model#instance-1"
    assert frames[-1]["message"]["model"] == "fake-model#instance-1"
    assert orch.history(session_key=request().session_key)[-1]["model"] == "fake-model#instance-1"
    answers = [a for a in orch._artifact_store.list_for_session(request().session_key) if a.type == "answer"]
    assert answers[0].metadata["model"] == "fake-model#instance-1"
    assert orch._session_store.get(request().session_key).model == "fake-model"


async def test_chart_delivery_failure_keeps_completed_admission(tmp_path):
    from test_chart_session import setup_chart

    orch, _, store, chart_request = setup_chart(tmp_path)

    async def emit(payload):
        raise RuntimeError("synthetic sink failure")

    assert (await orch.send_chat(chart_request, emit=emit))["status"] == "ok"
    assert (await orch.send_chat(chart_request, emit=noop))["status"] == "completed"


async def test_setup_failure_has_one_terminal_record(tmp_path, monkeypatch):
    orch = _orchestrator(tmp_path, ResolvingProvider())

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic setup failure")

    monkeypatch.setattr(orch._tool_registry, "list_tools", fail)
    result = await orch.send_chat(request(), emit=noop)
    assert result["status"] == "error"
    assert len(orch._run_store.list_for_session(request().session_key)) == 1
    assert not orch._active_run_by_session
