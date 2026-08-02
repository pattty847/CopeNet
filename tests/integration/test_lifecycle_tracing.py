"""Every run is traceable, whether or not Debug capture is on.

Before this, `runtime.py` built the trace writer with `enabled=debug_capture`, so a
run with the setting off wrote no trace at all — 672 runs had produced 341 trace
files. These tests pin the two halves of the fix: the lifecycle tier is
unconditional, and the payload-heavy tier is still gated.
"""

from __future__ import annotations

import asyncio

import pytest

from copenet.core.orchestrator import ChatSendRequest, Orchestrator
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent


class FakeProvider:
    name = "fake"
    display_name = "Fake"

    async def run(
        self,
        prompt: str,
        provider_session_id: str | None,
        abort_event: asyncio.Event,
        model: str | None = None,
        system_prompt: str | None = None,
    ):
        yield ProviderEvent(kind="delta", text="hello", provider_session_id=provider_session_id or "provider-session")
        yield ProviderEvent(kind="final")

    async def describe(self) -> dict:
        return {
            "id": self.name,
            "displayName": self.display_name,
            "available": True,
            "capabilities": {"chat": True, "streaming": True, "toolCalls": False},
        }


def _orchestrator(tmp_path) -> Orchestrator:
    return Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={"fake": FakeProvider()},
    )


async def _send(orchestrator: Orchestrator, session_key: str = "alpha") -> str:
    async def emit(payload: dict) -> None:
        return None

    result = await orchestrator.send_chat(
        ChatSendRequest(session_key=session_key, message="Hello", provider="fake", model="model-a"),
        emit=emit,
    )
    return result["runId"]


@pytest.mark.asyncio
async def test_a_run_writes_a_lifecycle_trace_with_debug_capture_off(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.update_observability_settings(debug_capture=False)

    run_id = await _send(orchestrator)

    events = orchestrator._observability_store.list_trace_events(run_id)
    names = [event["event"] for event in events]
    assert "run_started" in names
    assert "assistant_finalized" in names
    assert {event["tier"] for event in events} == {"lifecycle"}


@pytest.mark.asyncio
async def test_lifecycle_trace_carries_no_prompt_text(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.update_observability_settings(debug_capture=False)

    run_id = await _send(orchestrator)

    events = orchestrator._observability_store.list_trace_events(run_id)
    started = next(event for event in events if event["event"] == "run_started")
    assert "messagePreview" not in started["payload"]
    assert started["payload"]["messageChars"] == len("Hello")
    assert not [event for event in events if event["event"] in {"run_input", "tool_result_body"}]


@pytest.mark.asyncio
async def test_debug_capture_adds_the_payload_tier(tmp_path) -> None:
    orchestrator = _orchestrator(tmp_path)
    orchestrator.update_observability_settings(debug_capture=True)

    run_id = await _send(orchestrator)

    events = orchestrator._observability_store.list_trace_events(run_id)
    debug_events = [event for event in events if event["tier"] == "debug"]
    names = [event["event"] for event in debug_events]
    assert names == ["run_input", "model_input_snapshot"]
    assert debug_events[0]["payload"]["messagePreview"] == "Hello"


@pytest.mark.asyncio
async def test_debug_captured_flag_distinguishes_the_two_tiers(tmp_path) -> None:
    """`bool(events)` would now report every run as debug-captured — it must not."""
    orchestrator = _orchestrator(tmp_path)
    orchestrator.update_observability_settings(debug_capture=False)
    plain_run = await _send(orchestrator, session_key="plain")
    orchestrator.update_observability_settings(debug_capture=True)
    debug_run = await _send(orchestrator, session_key="deep")

    plain = orchestrator.resolve_observability_run("plain", plain_run)
    deep = orchestrator.resolve_observability_run("deep", debug_run)
    assert plain["lifecycleCaptured"] is True
    assert plain["debugCaptured"] is False
    assert deep["debugCaptured"] is True
