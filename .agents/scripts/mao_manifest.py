#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
from typing import Any

REQUIRED_FIELDS = {
    "run_id",
    "task_id",
    "objective",
    "assigned_agent",
    "branch",
    "worktree_path",
    "allowed_paths",
    "required_tests",
    "status",
    "scope_violation_count",
}


def normalize_repo_path(path: str) -> str:
    value = path.strip().replace("\\", "/")
    if value.startswith("./"):
        value = value[2:]
    return value


def validate_repo_path(path: str) -> str:
    value = normalize_repo_path(path)
    posix = PurePosixPath(value)
    if not value:
        raise ValueError("repo path must not be empty")
    if posix.is_absolute():
        raise ValueError(f"repo path must be relative: {path}")
    if ".." in posix.parts:
        raise ValueError(f"repo path must not contain parent traversal: {path}")
    return value


def validate_manifest(manifest: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_FIELDS - manifest.keys())
    if missing:
        raise ValueError(f"manifest missing required field(s): {', '.join(missing)}")

    allowed_paths = manifest["allowed_paths"]
    if not isinstance(allowed_paths, list) or not allowed_paths:
        raise ValueError("allowed_paths must be a non-empty list")
    manifest["allowed_paths"] = [validate_repo_path(str(path)) for path in allowed_paths]

    required_tests = manifest["required_tests"]
    if not isinstance(required_tests, list):
        raise ValueError("required_tests must be a list")

    manifest["worktree_path"] = validate_repo_path(str(manifest["worktree_path"]))
    manifest["scope_violation_count"] = int(manifest.get("scope_violation_count", 0))


def load_manifest(path: str | Path) -> dict[str, Any]:
    manifest_path = Path(path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("manifest must be a JSON object")
    validate_manifest(manifest)
    return manifest


def write_manifest(path: str | Path, manifest: dict[str, Any]) -> None:
    validate_manifest(manifest)
    manifest_path = Path(path)
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_active_manifest_path(repo_root: str | Path) -> Path | None:
    active_path = Path(repo_root) / ".agents" / "active-manifest"
    if not active_path.is_file():
        return None
    raw_value = active_path.read_text(encoding="utf-8").strip()
    if not raw_value:
        return None
    manifest_path = Path(raw_value)
    if not manifest_path.is_absolute():
        manifest_path = Path(repo_root) / manifest_path
    return manifest_path.resolve()


def run_dir_for_manifest(manifest_path: str | Path) -> Path:
    return Path(manifest_path).resolve().parent
