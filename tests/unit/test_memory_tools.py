from __future__ import annotations

from pathlib import Path

import pytest

from copenet.core.memory import MemoryService, MemoryStore
from copenet.core.runtime import ArtifactStore, RunRecord
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolPolicy, ToolRegistry


def _tool_context(tmp_path: Path, *, policy: ToolPolicy | None = None) -> ToolExecutionContext:
    memory_store = MemoryStore(tmp_path / "memory.json")
    memory_service = MemoryService(memory_store)
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="alpha",
        provider_name="prompted",
        model="test-model",
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path / "history"),
        providers={},
        policy=policy or ToolPolicy(),
        artifact_store=ArtifactStore(root_dir=tmp_path / "artifacts"),
        run_id="run-test",
        memory_service=memory_service,
    )


def test_memory_store_round_trips_and_archives_items(tmp_path: Path) -> None:
    store = MemoryStore(tmp_path / "memory.json")
    service = MemoryService(store)

    first = service.upsert_memory(
        category="preference",
        title="Tone",
        summary="Keep it warm and direct.",
        detail="The operator likes a casual, collaborative tone.",
        tags=["tone"],
    )
    archived = service.archive_memory(first.id)

    assert archived is not None
    assert archived.archived is True
    assert service.list_memory() == []
    assert service.list_memory(include_archived=True)[0].id == first.id


def test_memory_service_selects_relevant_digest_and_ignores_sensitive_input(tmp_path: Path) -> None:
    service = MemoryService(MemoryStore(tmp_path / "memory.json"))
    service.upsert_memory(
        category="ongoing_priority",
        title="Friend first",
        summary="CopeNet should feel like a friend with a workshop.",
        tags=["direction", "ux"],
    )
    service.upsert_memory(
        category="project_convention",
        title="Keep the theme",
        summary="Polish the custom theme instead of redesigning it.",
        tags=["frontend"],
    )

    payload = service.build_prompt_payload(query="keep the chat feeling like a friend and polish the theme")
    assert payload.digest is not None
    assert len(payload.memory_items) == 2

    chat_payload = service.build_prompt_payload(
        query="keep the chat feeling like a friend and polish the theme",
        limit=1,
    )
    assert len(chat_payload.memory_items) == 1

    extracted = service.extract_from_run(
        user_message="my api key is abc123 and please remember it forever",
        run_record=RunRecord(
            run_id="run-sensitive",
            session_key="alpha",
            provider="fake",
            model="model-a",
            status="ok",
            user_message="my api key is abc123 and please remember it forever",
            tool_execution_mode="none",
            will_attempt_tool_loop=False,
            output_summary="ok",
        ),
    )
    assert extracted.created == []


@pytest.mark.asyncio
async def test_memory_read_and_write_tools_persist_user_visible_memory(tmp_path: Path) -> None:
    registry = ToolRegistry()
    context = _tool_context(tmp_path, policy=ToolPolicy(allowed_categories={"repo-read", "repo-write", "shell-read", "context", "artifact"}))

    write_result = await registry.execute(
        ToolExecutionRequest(
            tool_id="memory.write",
            arguments={
                "category": "preference",
                "title": "Chat vibe",
                "summary": "Keep the conversation fluid and warm.",
                "detail": "Prefer friend-first language over sterile protocol voice.",
                "tags": ["tone", "conversation"],
            },
        ),
        context,
    )

    assert write_result.ok is True
    assert write_result.output["item"]["title"] == "Chat vibe"

    read_result = await registry.execute(
        ToolExecutionRequest(tool_id="memory.read", arguments={"query": "warm conversation", "limit": 3}),
        context,
    )

    assert read_result.ok is True
    assert read_result.output["count"] == 1
    assert read_result.output["items"][0]["summary"] == "Keep the conversation fluid and warm."
