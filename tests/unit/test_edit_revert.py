"""Edit-backup store + revert: record pre-edit content, undo a model's write/edit."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from copenet.core.runtime import EditBackupStore
from copenet.core.tools import ToolExecutionRequest, ToolPolicy, ToolRegistry
from copenet.core.tools.contracts import ToolExecutionContext
from copenet.core.sessions.session_store import SessionStore
from copenet.core.sessions.transcript_store import TranscriptStore


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def test_edit_backup_store_records_and_finds(tmp_path: Path) -> None:
    store = EditBackupStore(root_dir=tmp_path / "edit-backups")
    store.record(session_key="s1", path="a.txt", after_digest="d1", before_content="old", run_id="r1")
    found = store.find(session_key="s1", path="a.txt", after_digest="d1")
    assert found is not None
    assert found.before_content == "old"
    # wrong digest -> no match
    assert store.find(session_key="s1", path="a.txt", after_digest="nope") is None


def test_edit_backup_store_mark_reverted_clears_match(tmp_path: Path) -> None:
    store = EditBackupStore(root_dir=tmp_path / "edit-backups")
    store.record(session_key="s1", path="a.txt", after_digest="d1", before_content="old")
    store.mark_reverted(session_key="s1", path="a.txt", after_digest="d1")
    assert store.find(session_key="s1", path="a.txt", after_digest="d1") is None


def _write_context(tmp_path: Path, store: EditBackupStore) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="sess-edit",
        provider_name="test",
        model="test",
        session_store=SessionStore(path=tmp_path / "index.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        providers={},
        policy=ToolPolicy(allowed_categories={"repo-read", "repo-write", "shell-read", "context", "artifact"}),
        edit_backup_store=store,
        run_id="run-1",
    )


@pytest.mark.asyncio
async def test_edit_handler_records_backup_keyed_by_after_digest(tmp_path: Path) -> None:
    store = EditBackupStore(root_dir=tmp_path / "edit-backups")
    registry = ToolRegistry()
    path = tmp_path / "note.txt"
    path.write_text("alpha\nbeta\n", encoding="utf-8")

    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.edit", arguments={"path": "note.txt", "old_text": "beta", "new_text": "gamma"}),
        _write_context(tmp_path, store),
    )
    assert result.ok is True
    after_digest = result.output["digest"]
    backup = store.find(session_key="sess-edit", path="note.txt", after_digest=after_digest)
    assert backup is not None
    assert backup.before_content == "alpha\nbeta\n"
