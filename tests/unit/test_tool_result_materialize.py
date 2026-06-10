"""Large tool results must hand the MODEL real content, not a 280-char receipt.

Regression for the friction a phone-driven self-inspection surfaced: a large
files.read returned only {artifactId, preview} so the agent couldn't actually use
the file. The full output is still persisted as an artifact for the UI; the model
just gets the real text up to a configurable budget.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from copenet.core.harness.tool_loop import (
    _materialize_tool_result_artifact,
    model_facing_result_char_limit,
)
from copenet.core.tools import ToolExecutionResult, policy_for_task_mode
from copenet.core.tools.contracts import ToolExecutionContext
from copenet.core.sessions.session_store import SessionStore
from copenet.core.sessions.transcript_store import TranscriptStore


class _FakeArtifactStore:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def create(self, **kwargs):  # noqa: ANN003
        self.created.append(kwargs)
        return SimpleNamespace(artifact_id=f"art-{len(self.created)}")


def _ctx(tmp_path: Path) -> ToolExecutionContext:
    return ToolExecutionContext(
        workdir=tmp_path,
        session_workspace_root=tmp_path,
        session_key="s",
        provider_name="t",
        model="t",
        session_store=SessionStore(path=tmp_path / "i.json"),
        transcript_store=TranscriptStore(root_dir=tmp_path),
        providers={},
        policy=policy_for_task_mode("none"),
        artifact_store=_FakeArtifactStore(),
    )


def _read_result(content: str) -> ToolExecutionResult:
    return ToolExecutionResult(
        tool_id="files.read",
        ok=True,
        summary="Read file big.py",
        call_id="call-1",
        body={"path": "big.py", "content": content},
    )


def test_large_result_gives_model_real_content_not_a_receipt(tmp_path: Path) -> None:
    content = "X" * 9000  # > 4000 (persists artifact) but < 16000 (fits model budget)
    persisted, _ = _materialize_tool_result_artifact(
        tool_result=_read_result(content), tool_context=_ctx(tmp_path), trace=None
    )
    body = persisted.body
    assert isinstance(body, dict)
    assert body.get("artifactId")  # artifact still persisted for the UI
    assert body.get("content") == content  # the MODEL gets the actual file content
    assert "preview" not in body  # not the old 280-char receipt


def test_huge_result_is_clipped_to_budget_with_continuation(tmp_path: Path) -> None:
    content = "Y" * 40000  # well over the 16000 default model budget
    persisted, _ = _materialize_tool_result_artifact(
        tool_result=_read_result(content), tool_context=_ctx(tmp_path), trace=None
    )
    body = persisted.body
    assert body["truncatedForModel"] is True
    assert body["fullChars"] == len(_read_result(content).to_prompt_payload()) or body["fullChars"] > 16000
    assert len(body["content"]) <= model_facing_result_char_limit()
    assert "files.read again with a higher offset" in body["continuationHint"]
    assert body.get("artifactId")


def test_model_facing_budget_is_env_configurable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COPNET_MODEL_TOOL_RESULT_CHARS", "5000")
    assert model_facing_result_char_limit() == 5000
    content = "Z" * 9000  # now exceeds the lowered 5000 budget -> clipped
    persisted, _ = _materialize_tool_result_artifact(
        tool_result=_read_result(content), tool_context=_ctx(tmp_path), trace=None
    )
    assert persisted.body["truncatedForModel"] is True
    assert len(persisted.body["content"]) <= 5000


def test_small_result_passes_through_unchanged(tmp_path: Path) -> None:
    result = _read_result("small file body")
    persisted, _ = _materialize_tool_result_artifact(
        tool_result=result, tool_context=_ctx(tmp_path), trace=None
    )
    # under the 4000 threshold: no artifact, body untouched
    assert persisted.body == {"path": "big.py", "content": "small file body"}
    assert persisted.artifact_id is None
