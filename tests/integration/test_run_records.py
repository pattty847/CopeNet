import asyncio
import json

import pytest

from responses_fake import ScriptedResponsesProvider
from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.orchestrator import Orchestrator
from copenet.core.runtime import RunRecord, RunStore
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.providers import ProviderEvent


class ScriptedPromptedProvider(ScriptedResponsesProvider):
    """One output per model call: JSON {tool_id, arguments} becomes a tool call, anything else is the answer."""

    name = "prompted"
    display_name = "Prompted"

    def __init__(self, outputs: list[str]) -> None:
        super().__init__(outputs=outputs)


async def _collect_events(orchestrator: Orchestrator, request: ChatSendRequest) -> tuple[dict, list[dict]]:
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    result = await orchestrator.send_chat(request, emit=emit)
    return result, events


@pytest.mark.asyncio
async def test_send_chat_persists_run_record_for_multi_step_repo_exploration(tmp_path) -> None:
    (tmp_path / "README.md").write_text("# Temp Repo\nHello\n", encoding="utf-8")
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={
            "prompted": ScriptedPromptedProvider(
                outputs=[
                    '{"tool_id":"shell.exec","arguments":{"command":"ls ."}}',
                    '{"tool_id":"files.read","arguments":{"path":"README.md"}}',
                    "I inspected the repo and the README after listing files.",
                ]
            )
        },
    )

    result, events = await _collect_events(
        orchestrator,
        ChatSendRequest(session_key="alpha", message="Inspect the repository", provider="prompted"),
    )

    assert result["status"] == "ok"
    assert events[-1]["state"] == "final"
    runs = orchestrator._run_store.list_for_session("alpha")
    assert len(runs) == 1
    assert runs[0].status == "ok"
    assert [step["toolId"] for step in runs[0].tool_steps] == ["shell.exec", "files.read"]
    assert runs[0].artifact_ids
    assert "README" in runs[0].output_summary


def test_startup_recovery_does_not_replace_an_existing_terminal_run_record(tmp_path) -> None:
    session_store = SessionStore(path=tmp_path / "index.json")
    session_store.create_session(session_key="alpha", provider="prompted", model="model-a")
    session_store.mark_run_started("alpha", "run-terminal")
    run_store = RunStore(root_dir=tmp_path / "runs")
    run_store.create(
        RunRecord(
            run_id="run-terminal",
            session_key="alpha",
            provider="prompted",
            model="model-a",
            status="ok",
            user_message="already completed",
            tool_execution_mode="none",
            will_attempt_tool_loop=False,
            terminal_reason="completed",
        )
    )

    Orchestrator(
        session_store=session_store,
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={},
        recover_interrupted_runs=True,
    )

    entry = session_store.get("alpha")
    assert entry is not None
    assert entry.in_flight_run_id is None
    records = run_store.list_for_session("alpha")
    assert [(record.run_id, record.status) for record in records] == [("run-terminal", "ok")]


def test_non_host_orchestrator_does_not_recover_a_live_run(tmp_path) -> None:
    session_store = SessionStore(path=tmp_path / "index.json")
    session_store.create_session(session_key="alpha", provider="prompted", model="model-a")
    session_store.mark_run_started("alpha", "run-live")

    Orchestrator(
        session_store=session_store,
        transcript_store=TranscriptStore(root_dir=tmp_path),
        sessions_dir=tmp_path,
        providers={},
    )

    entry = session_store.get("alpha")
    assert entry is not None
    assert entry.in_flight_run_id == "run-live"
    assert RunStore(root_dir=tmp_path / "runs").list_for_session("alpha") == []
