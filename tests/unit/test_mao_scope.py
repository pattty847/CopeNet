from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
from pathlib import Path


def _load_scope_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / ".agents" / "scripts" / "mao_check_scope.py"
    spec = importlib.util.spec_from_file_location("mao_check_scope", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_manifest_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / ".agents" / "scripts" / "mao_manifest.py"
    spec = importlib.util.spec_from_file_location("mao_manifest", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(cmd: list[str], cwd: Path, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["GIT_AUTHOR_NAME"] = "MAO Test"
    env["GIT_AUTHOR_EMAIL"] = "mao@example.invalid"
    env["GIT_COMMITTER_NAME"] = "MAO Test"
    env["GIT_COMMITTER_EMAIL"] = "mao@example.invalid"
    return subprocess.run(cmd, cwd=cwd, env=env, check=check, text=True, capture_output=True)


def _write_manifest(path: Path, allowed_paths: list[str]) -> None:
    payload = {
        "run_id": "v0-pilot-01",
        "task_id": "T-01",
        "objective": "Test scope enforcement.",
        "assigned_agent": "codex",
        "branch": "agent/codex/T-01-agents-ping",
        "worktree_path": ".agents/worktrees/T-01-agents-ping",
        "allowed_paths": allowed_paths,
        "required_tests": ["python -m pytest"],
        "status": "ready",
        "scope_violation_count": 0,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _init_repo(tmp_path: Path, allowed_paths: list[str]) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)
    (repo / ".agents").mkdir()
    run_dir = repo / ".agents" / "runs" / "v0-pilot-01"
    run_dir.mkdir(parents=True)
    manifest_path = run_dir / "manifest.json"
    _write_manifest(manifest_path, allowed_paths)
    (repo / ".agents" / "active-manifest").write_text(str(manifest_path), encoding="utf-8")
    return repo, manifest_path


def test_staged_file_exactly_matching_allowed_file_passes(tmp_path: Path) -> None:
    mao_check_scope = _load_scope_module()
    repo, manifest_path = _init_repo(tmp_path, ["src/copenet/host/app_api.py"])
    target = repo / "src" / "copenet" / "host" / "app_api.py"
    target.parent.mkdir(parents=True)
    target.write_text("# route\n", encoding="utf-8")
    _run(["git", "add", "src/copenet/host/app_api.py"], repo)

    result = mao_check_scope.check_scope(repo, manifest_path)

    assert result.ok is True
    assert result.illegal_paths == []


def test_new_file_under_allowed_directory_passes(tmp_path: Path) -> None:
    mao_check_scope = _load_scope_module()
    repo, manifest_path = _init_repo(tmp_path, ["tests/integration/"])
    target = repo / "tests" / "integration" / "test_app_api_agents.py"
    target.parent.mkdir(parents=True)
    target.write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
    _run(["git", "add", "tests/integration/test_app_api_agents.py"], repo)

    result = mao_check_scope.check_scope(repo, manifest_path)

    assert result.ok is True


def test_file_outside_allowed_paths_fails_and_increments_count(tmp_path: Path) -> None:
    mao_check_scope = _load_scope_module()
    mao_manifest = _load_manifest_module()
    repo, manifest_path = _init_repo(tmp_path, ["src/copenet/host/app_api.py"])
    target = repo / "README.md"
    target.write_text("illegal\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo)

    result = mao_check_scope.record_scope_result(repo, manifest_path)

    manifest = mao_manifest.load_manifest(manifest_path)
    assert result.ok is False
    assert result.illegal_paths == ["README.md"]
    assert manifest["scope_violation_count"] == 1
    assert manifest["status"] == "ready"


def test_second_scope_violation_marks_manifest_blocked(tmp_path: Path) -> None:
    mao_check_scope = _load_scope_module()
    mao_manifest = _load_manifest_module()
    repo, manifest_path = _init_repo(tmp_path, ["src/copenet/host/app_api.py"])
    manifest = mao_manifest.load_manifest(manifest_path)
    manifest["scope_violation_count"] = 1
    mao_manifest.write_manifest(manifest_path, manifest)
    target = repo / "README.md"
    target.write_text("illegal\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo)

    result = mao_check_scope.record_scope_result(repo, manifest_path)

    manifest = mao_manifest.load_manifest(manifest_path)
    report = manifest_path.parent / "escalation-report.md"
    assert result.ok is False
    assert manifest["scope_violation_count"] == 2
    assert manifest["status"] == "blocked"
    assert "README.md" in report.read_text(encoding="utf-8")


def test_pre_commit_noops_without_active_manifest(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    hook = root / ".agents" / "hooks" / "pre-commit"
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init"], repo)

    result = _run([str(hook)], repo, check=False)

    assert result.returncode == 0


def test_pre_commit_rejects_illegal_staged_file_with_cage_message(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    hook = root / ".agents" / "hooks" / "pre-commit"
    repo, _ = _init_repo(tmp_path, ["src/copenet/host/app_api.py"])
    target = repo / "README.md"
    target.write_text("illegal\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo)

    result = _run([str(hook)], repo, check=False)

    assert result.returncode == 1
    assert "BACK TO THE CAGE: BONK" in result.stderr
    assert "README.md" in result.stderr


def test_commit_msg_rejects_messages_without_task_prefix(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    hook = root / ".agents" / "hooks" / "commit-msg"
    repo, _ = _init_repo(tmp_path, ["src/copenet/host/app_api.py"])
    message = repo / "COMMIT_EDITMSG"
    message.write_text("add endpoint\n", encoding="utf-8")

    result = _run([str(hook), str(message)], repo, check=False)

    assert result.returncode == 1
    assert "must start with [T-01]" in result.stderr


def test_installed_pre_commit_resolves_repo_local_scripts(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[2]
    repo, _ = _init_repo(tmp_path, ["src/copenet/host/app_api.py"])
    shutil.copytree(root / ".agents" / "scripts", repo / ".agents" / "scripts")
    install_script = root / ".agents" / "scripts" / "mao_install_hooks.py"
    _run(["python3", str(install_script), "--worktree", str(repo)], repo)
    target = repo / "README.md"
    target.write_text("illegal\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo)

    result = _run(["git", "commit", "-m", "[T-01] illegal edit"], repo, check=False)

    assert result.returncode == 1
    assert "BACK TO THE CAGE: BONK" in result.stderr
