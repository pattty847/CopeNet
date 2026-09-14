from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from copenet.core.runtime import ArtifactStore
from copenet.core.sessions import SessionStore, TranscriptStore
from copenet.core.tools import ToolExecutionContext, ToolExecutionRequest, ToolPolicy, ToolRegistry


def _tool_context(tmp_path: Path, *, policy: ToolPolicy | None = None) -> ToolExecutionContext:
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
    )


@pytest.mark.asyncio
async def test_files_rg_returns_bounded_matches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry = ToolRegistry()

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=(
                '{"type":"match","data":{"path":{"text":"src/app.py"},"lines":{"text":"needle appears here\\n"},"line_number":12,"submatches":[{"match":{"text":"needle"},"start":4,"end":10}]}}\n'
                '{"type":"match","data":{"path":{"text":"README.md"},"lines":{"text":"needle again\\n"},"line_number":3,"submatches":[{"match":{"text":"needle"},"start":0,"end":6}]}}\n'
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.rg", arguments={"pattern": "needle", "path": "."}),
        _tool_context(tmp_path),
    )

    assert result.ok is True
    # Phase 0.2: summary now reports both total and returned page counts.
    assert result.summary == "Found 2 matches for pattern via ripgrep; returning 2."
    assert result.output["totalMatches"] == 2
    assert result.output["truncated"] is False
    assert result.output["scope"] == "inside_workspace"
    assert result.output["workspaceRoot"] == str(tmp_path)
    assert result.output["matches"] == [
        {"path": "src/app.py", "line": 12, "column": 5, "text": "needle appears here"},
        {"path": "README.md", "line": 3, "column": 1, "text": "needle again"},
    ]


@pytest.mark.asyncio
async def test_files_rg_fails_clearly_when_rg_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    registry = ToolRegistry()

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("rg")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.rg", arguments={"pattern": "needle", "path": "."}),
        _tool_context(tmp_path),
    )

    assert result.ok is False
    assert result.error == "ripgrep (rg) is not installed or not available on PATH"


@pytest.mark.asyncio
async def test_files_read_allows_outside_workspace_and_marks_scope(tmp_path: Path) -> None:
    registry = ToolRegistry()
    outside_root = tmp_path.parent / f"{tmp_path.name}-outside"
    outside_root.mkdir(exist_ok=True)
    outside_file = outside_root / "note.txt"
    outside_file.write_text("hello from outside\n", encoding="utf-8")

    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.read", arguments={"path": str(outside_file)}),
        _tool_context(tmp_path),
    )

    assert result.ok is True
    assert result.output["scope"] == "outside_workspace"
    assert result.output["workspaceRoot"] == str(tmp_path)
    assert result.output["target"] == str(outside_file)
    assert result.output["path"] == str(outside_file)


@pytest.mark.asyncio
async def test_files_write_creates_file_inside_workspace_when_policy_allows(tmp_path: Path) -> None:
    registry = ToolRegistry()
    context = _tool_context(tmp_path, policy=ToolPolicy(allowed_categories={"repo-read", "repo-write", "shell-read", "context", "artifact"}))

    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.write", arguments={"path": "docs/tests/generated.md", "content": "hello write tool\n"}),
        context,
    )

    assert result.ok is True
    assert (tmp_path / "docs/tests/generated.md").read_text(encoding="utf-8") == "hello write tool\n"
    assert result.output["target"] == "docs/tests/generated.md"
    assert result.output["accessAction"] == "write"


@pytest.mark.asyncio
async def test_files_edit_replaces_targeted_text_inside_workspace(tmp_path: Path) -> None:
    registry = ToolRegistry()
    context = _tool_context(tmp_path, policy=ToolPolicy(allowed_categories={"repo-read", "repo-write", "shell-read", "context", "artifact"}))
    path = tmp_path / "README.md"
    path.write_text("before\nreplace me\nafter\n", encoding="utf-8")

    result = await registry.execute(
        ToolExecutionRequest(
            tool_id="files.edit",
            arguments={"path": "README.md", "old_text": "replace me", "new_text": "replaced"},
        ),
        context,
    )

    assert result.ok is True
    assert path.read_text(encoding="utf-8") == "before\nreplaced\nafter\n"
    assert result.output["target"] == "README.md"
    assert result.output["accessAction"] == "write"


@pytest.mark.asyncio
async def test_files_edit_emits_unified_diff(tmp_path: Path) -> None:
    registry = ToolRegistry()
    context = _tool_context(tmp_path, policy=ToolPolicy(allowed_categories={"repo-read", "repo-write", "shell-read", "context", "artifact"}))
    path = tmp_path / "README.md"
    path.write_text("line one\nreplace me\nline three\n", encoding="utf-8")

    result = await registry.execute(
        ToolExecutionRequest(
            tool_id="files.edit",
            arguments={"path": "README.md", "old_text": "replace me", "new_text": "replaced"},
        ),
        context,
    )

    assert result.ok is True
    assert "-replace me" in result.output["diff"]
    assert "+replaced" in result.output["diff"]
    assert result.output["linesAdded"] == 1
    assert result.output["linesRemoved"] == 1
    assert result.output["diffTruncated"] is False


@pytest.mark.asyncio
async def test_files_write_new_file_emits_diff_and_created_flag(tmp_path: Path) -> None:
    registry = ToolRegistry()
    context = _tool_context(tmp_path, policy=ToolPolicy(allowed_categories={"repo-read", "repo-write", "shell-read", "context", "artifact"}))

    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.write", arguments={"path": "new.md", "content": "alpha\nbeta\n"}),
        context,
    )

    assert result.ok is True
    assert result.output["created"] is True
    assert result.output["linesAdded"] == 2
    assert result.output["linesRemoved"] == 0
    assert "+alpha" in result.output["diff"]


@pytest.mark.asyncio
async def test_repo_write_tools_are_blocked_when_policy_disallows_writes(tmp_path: Path) -> None:
    registry = ToolRegistry()

    result = await registry.execute(
        ToolExecutionRequest(tool_id="files.write", arguments={"path": "blocked.md", "content": "nope"}),
        _tool_context(tmp_path),
    )

    assert result.ok is False
    assert result.error == "write tool unavailable in current mode"
    assert result.output["policyDecision"] == "write_blocked"


@pytest.mark.asyncio
async def test_artifact_create_persists_summary_artifact(tmp_path: Path) -> None:
    registry = ToolRegistry()
    context = _tool_context(tmp_path)

    result = await registry.execute(
        ToolExecutionRequest(
            tool_id="artifact.create",
            arguments={"title": "Proof Note", "body": "Artifact body for the run.", "artifact_type": "summary"},
        ),
        context,
    )

    assert result.ok is True
    assert result.artifact_id
    records = context.artifact_store.list_for_session("alpha")
    assert len(records) == 1
    assert records[0].title == "Proof Note"
    assert records[0].type == "summary"
    assert "artifactId" in result.output


def _match_line(path: str, line: int) -> str:
    return (
        '{"type":"match","data":{"path":{"text":"%s"},"lines":{"text":"needle here\\n"},"line_number":%d,'
        '"submatches":[{"match":{"text":"needle"},"start":0,"end":6}]}}\n' % (path, line)
    )


@pytest.mark.asyncio
async def test_files_rg_overflow_returns_a_per_file_map_and_a_small_sample(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Past the 200-match cap a page is an arbitrary sample; the per-file map is the orientation the model needed."""
    stdout = "".join(_match_line("src/a.py", i) for i in range(150)) + "".join(_match_line("src/b.py", i) for i in range(60)) + "".join(_match_line("docs/c.md", i) for i in range(40))

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = await ToolRegistry().execute(ToolExecutionRequest("files.rg", {"pattern": "needle", "path": ".", "limit": 120}), _tool_context(tmp_path))

    assert result.ok is True
    assert result.summary.startswith("Found 250 matches across 3 files — too broad to read through.")
    assert "most matches: src/a.py ×150" in result.summary
    assert result.output["totalMatches"] == 250 and result.output["fileCount"] == 3
    assert result.output["byFile"] == [{"path": "src/a.py", "matches": 150}, {"path": "src/b.py", "matches": 60}, {"path": "docs/c.md", "matches": 40}]
    assert len(result.output["matches"]) == 25 and result.output["truncated"] is True and result.output["nextOffset"] == 25


@pytest.mark.asyncio
async def test_files_rg_accepts_several_search_roots(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    seen: dict[str, list[str]] = {}

    def fake_run(argv, *args, **kwargs):
        seen["argv"] = list(argv)
        return subprocess.CompletedProcess(args=argv, returncode=1, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    registry = ToolRegistry()
    result = await registry.execute(ToolExecutionRequest("files.rg", {"pattern": "needle", "path": "tests src"}), _tool_context(tmp_path))
    assert result.ok is True and result.output["paths"] == ["tests", "src"]
    assert seen["argv"][-2:] == [str(tmp_path / "tests"), str(tmp_path / "src")]

    missing = await registry.execute(ToolExecutionRequest("files.rg", {"pattern": "needle", "path": "tests nowhere"}), _tool_context(tmp_path))
    assert missing.ok is False and "nowhere" in str(missing.error) and "several separated by spaces" in str(missing.error)
