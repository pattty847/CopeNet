#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mao_manifest import load_manifest, read_active_manifest_path, run_dir_for_manifest, validate_repo_path, write_manifest


class ScopeResult(NamedTuple):
    ok: bool
    illegal_paths: list[str]
    staged_paths: list[str]


def _git(args: list[str], cwd: Path) -> str:
    completed = subprocess.run(["git", *args], cwd=cwd, check=True, text=True, capture_output=True)
    return completed.stdout


def repo_root_for(cwd: str | Path) -> Path:
    return Path(_git(["rev-parse", "--show-toplevel"], Path(cwd)).strip())


def staged_paths(repo_root: str | Path) -> list[str]:
    output = _git(["diff", "--cached", "--name-only", "--diff-filter=ACMR"], Path(repo_root))
    return [validate_repo_path(line) for line in output.splitlines() if line.strip()]


def is_path_allowed(path: str, allowed_paths: list[str]) -> bool:
    candidate = validate_repo_path(path)
    for allowed in allowed_paths:
        normalized = validate_repo_path(allowed)
        if normalized.endswith("/"):
            if candidate.startswith(normalized):
                return True
        elif candidate == normalized or candidate.startswith(f"{normalized}/"):
            return True
    return False


def check_scope(repo_root: str | Path, manifest_path: str | Path) -> ScopeResult:
    manifest = load_manifest(manifest_path)
    staged = staged_paths(repo_root)
    illegal = [path for path in staged if not is_path_allowed(path, manifest["allowed_paths"])]
    return ScopeResult(ok=not illegal, illegal_paths=illegal, staged_paths=staged)


def _write_escalation_report(manifest_path: Path, result: ScopeResult) -> None:
    manifest = load_manifest(manifest_path)
    report = run_dir_for_manifest(manifest_path) / "escalation-report.md"
    lines = [
        f"# Scope Escalation: {manifest['task_id']}",
        "",
        "The worker hit the scope circuit breaker.",
        "",
        "Illegal staged files:",
        *[f"- {path}" for path in result.illegal_paths],
        "",
    ]
    report.write_text("\n".join(lines), encoding="utf-8")


def record_scope_result(repo_root: str | Path, manifest_path: str | Path) -> ScopeResult:
    resolved_manifest_path = Path(manifest_path)
    result = check_scope(repo_root, resolved_manifest_path)
    if result.ok:
        return result

    manifest = load_manifest(resolved_manifest_path)
    manifest["scope_violation_count"] = int(manifest.get("scope_violation_count", 0)) + 1
    if manifest["scope_violation_count"] >= 2:
        manifest["status"] = "blocked"
    write_manifest(resolved_manifest_path, manifest)
    if manifest["status"] == "blocked":
        _write_escalation_report(resolved_manifest_path, result)
    return result


def _format_failure(manifest_path: Path, result: ScopeResult) -> str:
    manifest = load_manifest(manifest_path)
    allowed = "\n".join(f"- {path}" for path in manifest["allowed_paths"])
    illegal = "\n".join(f"- {path}" for path in result.illegal_paths)
    header = "BACK TO THE CAGE: BONK"
    if manifest["status"] == "blocked":
        header = "BACK TO THE CAGE: BONK\nTask blocked after second scope violation."
    return (
        f"{header}\n"
        f"Task {manifest['task_id']} may only edit:\n"
        f"{allowed}\n"
        "Illegal staged file(s):\n"
        f"{illegal}\n"
        "Commit rejected.\n"
    )


def main() -> int:
    repo_root = repo_root_for(Path.cwd())
    manifest_path = read_active_manifest_path(repo_root)
    if manifest_path is None:
        return 0
    result = record_scope_result(repo_root, manifest_path)
    if result.ok:
        return 0
    sys.stderr.write(_format_failure(manifest_path, result))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
