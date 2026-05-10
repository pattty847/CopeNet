from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


def _load_manifest_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / ".agents" / "scripts" / "mao_manifest.py"
    spec = importlib.util.spec_from_file_location("mao_manifest", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_manifest(path: Path, **overrides: object) -> None:
    payload = {
        "run_id": "v0-pilot-01",
        "task_id": "T-01",
        "objective": "Add GET /api/v1/agents/ping with one test.",
        "assigned_agent": "codex",
        "branch": "agent/codex/T-01-agents-ping",
        "worktree_path": ".agents/worktrees/T-01-agents-ping",
        "allowed_paths": ["src/copenet/host/app_api.py", "tests/integration/test_app_api_agents.py"],
        "required_tests": ["uv run --extra dev pytest -q tests/integration/test_app_api_agents.py"],
        "status": "ready",
        "scope_violation_count": 0,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_load_manifest_rejects_missing_required_field(tmp_path: Path) -> None:
    mao_manifest = _load_manifest_module()
    path = tmp_path / "manifest.json"
    _write_manifest(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["task_id"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="task_id"):
        mao_manifest.load_manifest(path)


def test_load_manifest_rejects_empty_allowed_paths(tmp_path: Path) -> None:
    mao_manifest = _load_manifest_module()
    path = tmp_path / "manifest.json"
    _write_manifest(path, allowed_paths=[])

    with pytest.raises(ValueError, match="allowed_paths"):
        mao_manifest.load_manifest(path)


def test_load_manifest_rejects_absolute_or_parent_paths(tmp_path: Path) -> None:
    mao_manifest = _load_manifest_module()
    path = tmp_path / "manifest.json"

    _write_manifest(path, allowed_paths=["/tmp/outside.py"])
    with pytest.raises(ValueError, match="relative"):
        mao_manifest.load_manifest(path)

    _write_manifest(path, allowed_paths=["../outside.py"])
    with pytest.raises(ValueError, match="parent"):
        mao_manifest.load_manifest(path)


def test_load_manifest_accepts_valid_manifest(tmp_path: Path) -> None:
    mao_manifest = _load_manifest_module()
    path = tmp_path / "manifest.json"
    _write_manifest(path)

    manifest = mao_manifest.load_manifest(path)

    assert manifest["run_id"] == "v0-pilot-01"
    assert manifest["task_id"] == "T-01"
    assert manifest["status"] == "ready"
