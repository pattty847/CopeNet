"""Deferred disclosure through the orchestrator: catalog first, tools.load, sticky for the session."""

from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.orchestrator import Orchestrator
from copenet.core.orchestrator.requests import ChatSendRequest
from copenet.core.sessions import SessionStore, TranscriptStore
from responses_fake import ScriptedResponsesProvider


async def _send(orchestrator: Orchestrator, provider: ScriptedResponsesProvider, workspace: Path, message: str, run_id: str) -> None:
    async def emit(payload: dict) -> None:
        return None

    result = await orchestrator.send_chat(
        ChatSendRequest(session_key="deferred-session", message=message, idempotency_key=run_id, provider=provider.name, task_prompt_id="full-access", workspace_root=str(workspace)),
        emit=emit,
    )
    assert result["status"] == "ok", result


@pytest.mark.asyncio
async def test_catalog_then_load_then_sticky_across_turns(tmp_path: Path) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    provider = ScriptedResponsesProvider(
        outputs=[
            # turn 1: the model asks for a deferred tool, then uses it
            '{"tool_id": "tools.load", "arguments": {"tool_ids": ["memory.write"]}}',
            '{"tool_id": "memory.write", "arguments": {"kind": "fact", "content": "This repo is the deferred-tools fixture."}}',
            "Saved a draft.",
            # turn 2: answer directly; we inspect what it was offered
            "Nothing to do.",
        ]
    )
    orchestrator = Orchestrator(
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        sessions_dir=tmp_path,
        providers={provider.name: provider},
    )
    await _send(orchestrator, provider, workspace, "Remember this repo", "run-1")

    # step 1 of turn 1: the core set only, with the catalog in the system prompt
    first_tools = provider.tool_names[0]
    assert "tools.load" in first_tools and "files.read" in first_tools
    assert "memory.write" not in first_tools and "market.ticker" not in first_tools
    assert "<deferred_tools>" in (provider.instructions[0] or "")
    assert "- memory.write — " in provider.instructions[0]
    # step 2 of turn 1: memory.write is in the schema list because tools.load ran
    assert "memory.write" in provider.tool_names[1]
    # and it actually dispatched (not "unknown tool")
    history = orchestrator.history(session_key="deferred-session")
    executions = [part["toolExecution"] for row in history if row["role"] == "assistant" for part in row["parts"] if part["kind"] == "tool_result"]
    memory_step = next(step for step in executions if step["toolId"] == "memory.write")
    assert "Unknown tools are blocked" not in str(memory_step.get("policySummary") or "")
    assert orchestrator._session_state_store.get("deferred-session").loaded_tool_ids == ["memory.write"]

    await _send(orchestrator, provider, workspace, "Anything else?", "run-2")
    # turn 2 starts with memory.write loaded and no longer in the catalog
    turn2_tools = provider.tool_names[-1]
    assert "memory.write" in turn2_tools
    assert "- memory.write — " not in (provider.instructions[-1] or "")
    assert "- market.ticker — " in provider.instructions[-1]
