"""Three turns through the orchestrator: turn 3 sees turn 1 as receipts, turn 2 verbatim, edits and failures intact."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from copenet.core.orchestrator import Orchestrator
from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.sessions import SessionStore, TranscriptStore
from responses_fake import ScriptedResponsesProvider, tool_outputs


async def _send(orchestrator: Orchestrator, provider: ScriptedResponsesProvider, workspace: Path, message: str, run_id: str) -> None:
    async def emit(payload: dict) -> None:
        return None

    result = await orchestrator.send_chat(
        ChatSendRequest(session_key="receipt-session", message=message, idempotency_key=run_id, provider=provider.name, task_prompt_id="full-access", workspace_root=str(workspace)),
        emit=emit,
    )
    assert result["status"] == "ok", result


@pytest.mark.asyncio
async def test_old_turn_reads_replay_as_receipts_while_edits_and_failures_stay_verbatim(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "app.py").write_text("VALUE = 1\n# " + "padding " * 200 + "\n", encoding="utf-8")
    provider = ScriptedResponsesProvider(
        outputs=[
            # turn 1: read, a failing command, an edit, then answer
            '{"tool_id": "files.read", "arguments": {"path": "app.py"}}',
            '{"tool_id": "shell.exec", "arguments": {"command": "python -c \\"import sys; print(\'boom\'); sys.exit(3)\\""}}',
            '{"tool_id": "files.edit", "arguments": {"path": "app.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"}}',
            "Turn one done.",
            # turn 2: one read, then answer
            '{"tool_id": "files.read", "arguments": {"path": "app.py", "start_line": 1, "end_line": 1}}',
            "Turn two done.",
            # turn 3: answer directly; we inspect what it was shown
            "Turn three done.",
        ]
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={provider.name: provider},
    )
    await _send(orchestrator, provider, workspace, "Bump VALUE", "run-1")
    await _send(orchestrator, provider, workspace, "Check the first line", "run-2")
    await _send(orchestrator, provider, workspace, "Summarize", "run-3")

    turn3_input = provider.messages[-1]
    outputs = [json.loads(item["output"]) for item in tool_outputs(turn3_input)]
    by_tool = {}
    for envelope in outputs:
        by_tool.setdefault(envelope["toolId"], []).append(envelope)

    # turn 1 read: receipt — no content, but path and digest survive
    old_read, recent_read = by_tool["files.read"]
    assert "padding" not in json.dumps(old_read) and old_read["body"]["path"] == "app.py" and old_read["body"]["digest"]
    assert "turn 1" in old_read["body"]["elided"]
    # turn 1 failed command: verbatim, with the error
    failed = by_tool["shell.exec"][0]
    assert failed["ok"] is False and "boom" in failed["body"]["stdout"] and failed["body"]["exitCode"] == 3
    # turn 1 edit: verbatim diff
    edit = by_tool["files.edit"][0]
    assert "+VALUE = 2" in edit["body"]["diff"]
    # turn 2 (most recent completed turn): verbatim content
    assert recent_read["body"]["content"] == "VALUE = 2"
    # the durable transcript still holds the full turn-1 read for the UI
    history = orchestrator.history(session_key="receipt-session")
    first_turn_parts = next(row for row in history if row["role"] == "assistant")["parts"]
    stored = next(part["toolExecution"]["replayOutput"] for part in first_turn_parts if part["kind"] == "tool_result")
    assert "padding" in stored
