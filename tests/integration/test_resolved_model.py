"""A run is stamped with the model that answered, not the one that was requested.

Before this, both the trace writer and `RunRecord` took `request.model`. Measured
2026-08-01: 95 of 334 local traces (28%) carried a null model, so more than a
quarter of run history could not say what produced it. The divergence is real —
LM Studio resolves a request against whichever instance is loaded.
"""

from __future__ import annotations

import asyncio

import pytest

from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.orchestrator import Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent, resolved_model_event


class ResolvingProvider:
    """Answers as a different model id than the one requested."""

    name = "fake"
    display_name = "Fake"

    def __init__(self, *, resolved: str | None = "fake-model#instance-1") -> None:
        self.resolved = resolved

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        announcement = resolved_model_event(self.resolved)
        if announcement is not None:
            yield announcement
        yield ProviderEvent(kind="delta", text="hello", provider_session_id="provider-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False},
        }


def _orchestrator(tmp_path, provider) -> Orchestrator:
    return Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={"fake": provider},
    )


async def _send(orchestrator: Orchestrator, session_key: str = "alpha") -> str:
    async def emit(payload: dict) -> None:
        return None

    result = await orchestrator.send_chat(
        ChatSendRequest(session_key=session_key, message="Hi", provider="fake", model="fake-model"),
        emit=emit,
    )
    return result["runId"]


@pytest.mark.asyncio
async def test_the_run_record_carries_the_answering_model(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, ResolvingProvider())
    run_id = await _send(orchestrator)

    run = orchestrator.resolve_session_run("alpha", run_id)
    assert run is not None
    assert run["model"] == "fake-model#instance-1"


@pytest.mark.asyncio
async def test_the_trace_retags_mid_run_and_records_the_swap(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path, ResolvingProvider())
    run_id = await _send(orchestrator)

    events = orchestrator._observability_store.list_trace_events(run_id)
    swap = next(event for event in events if event["event"] == "model_resolved")
    assert swap["payload"] == {"requestedModel": "fake-model", "resolvedModel": "fake-model#instance-1"}

    # Rows before the announcement keep the requested id; everything after carries
    # the answering one, so the swap point is visible rather than rewritten.
    assert events[0]["model"] == "fake-model"
    assert events[-1]["model"] == "fake-model#instance-1"


@pytest.mark.asyncio
async def test_a_provider_that_reports_nothing_falls_back_to_the_request(tmp_path) -> None:
    """Every provider announcing is not a precondition — silence must stay safe."""
    orchestrator = _orchestrator(tmp_path, ResolvingProvider(resolved=None))
    run_id = await _send(orchestrator)

    run = orchestrator.resolve_session_run("alpha", run_id)
    assert run is not None
    assert run["model"] == "fake-model"
    events = orchestrator._observability_store.list_trace_events(run_id)
    assert not [event for event in events if event["event"] == "model_resolved"]
