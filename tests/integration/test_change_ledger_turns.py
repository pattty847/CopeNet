"""The change ledger reaches the next turn and seeds cross-turn edit freshness."""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.orchestrator import Orchestrator
from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.sessions.change_ledger import LEDGER_HEADER
from responses_fake import ScriptedResponsesProvider, tool_outputs, user_texts


def _orchestrator(tmp_path: Path, provider: ScriptedResponsesProvider) -> Orchestrator:
    return Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={provider.name: provider},
    )


async def _send(orchestrator: Orchestrator, provider: ScriptedResponsesProvider, workspace: Path, message: str, run_id: str) -> dict:
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    result = await orchestrator.send_chat(
        ChatSendRequest(
            session_key="ledger-session",
            message=message,
            idempotency_key=run_id,
            provider=provider.name,
            task_prompt_id="full-access",
            workspace_root=str(workspace),
        ),
        emit=emit,
    )
    assert result["status"] == "ok", result
    return {"events": events}


@pytest.mark.asyncio
async def test_second_turn_sees_the_ledger_and_history_replay_stays_clean(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    provider = ScriptedResponsesProvider(
        outputs=[
            '{"tool_id": "files.edit", "arguments": {"path": "app.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}}',
            "Bumped VALUE.",
            "Nothing more to do.",
        ]
    )
    orchestrator = _orchestrator(tmp_path, provider)

    await _send(orchestrator, provider, workspace, "Bump VALUE to 2", "run-1")
    # Turn 1's own live message carries no ledger: nothing had changed yet.
    assert LEDGER_HEADER not in user_texts(provider.messages[0])[-1]

    await _send(orchestrator, provider, workspace, "What did you change?", "run-2")
    turn2_live = user_texts(provider.messages[-1])[-1]
    assert turn2_live.startswith("What did you change?")
    assert LEDGER_HEADER in turn2_live
    assert "- app.py: edited (turn 1, +1/−1); on disk as you left it" in turn2_live
    # The replayed turn-1 user message is the operator's words only, never a stale ledger.
    assert LEDGER_HEADER not in user_texts(provider.messages[-1])[0]
    # The durable transcript stores the operator's message, not the augmented one.
    history = orchestrator.history(session_key="ledger-session")
    assert [row["content"] for row in history if row["role"] == "user"] == ["Bump VALUE to 2", "What did you change?"]


@pytest.mark.asyncio
async def test_ledger_flags_operator_drift_and_the_freshness_gate_refuses_a_blind_edit(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    provider = ScriptedResponsesProvider(
        outputs=[
            '{"tool_id": "files.edit", "arguments": {"path": "app.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}}',
            "Bumped VALUE.",
            # Turn 2: edit without re-reading, even though the operator changed the file meanwhile.
            '{"tool_id": "files.edit", "arguments": {"path": "app.py", "old_text": "VALUE = 3", "new_text": "VALUE = 4"}}',
            "Tried again.",
        ]
    )
    orchestrator = _orchestrator(tmp_path, provider)
    await _send(orchestrator, provider, workspace, "Bump VALUE to 2", "run-1")

    (workspace / "app.py").write_text("VALUE = 3\n", encoding="utf-8")  # operator edits between turns
    await _send(orchestrator, provider, workspace, "Bump it again", "run-2")

    turn2_live = user_texts(provider.messages[2])[-1]
    assert "CHANGED ON DISK since your last edit" in turn2_live
    refused = tool_outputs(provider.messages[3])[-1]["output"]
    assert '"ok": false' in refused
    assert "changed on disk since you last read it in this run" in refused
    assert (workspace / "app.py").read_text(encoding="utf-8") == "VALUE = 3\n"
