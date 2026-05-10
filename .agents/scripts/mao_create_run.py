#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mao_manifest import write_manifest


def _repo_root() -> Path:
    completed = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True, text=True, capture_output=True)
    return Path(completed.stdout.strip())


def _write_brief(run_dir: Path, manifest: dict[str, object]) -> None:
    allowed_paths = "\n".join(f"- {path}" for path in manifest["allowed_paths"])
    required_tests = "\n".join(f"- `{command}`" for command in manifest["required_tests"])
    brief = f"""# Worker Brief: {manifest["task_id"]}

Objective:
{manifest["objective"]}

Worktree:
`{manifest["worktree_path"]}`

Branch:
`{manifest["branch"]}`

Allowed paths:
{allowed_paths}

Everything else is blocked by default.

Required tests:
{required_tests}

Commit message:
Start the first line with `[{manifest["task_id"]}]`.

Stop and report if you need to edit outside the allowed paths, the task is larger than described, or required tests fail for reasons unrelated to your change.
"""
    (run_dir / "brief.md").write_text(brief, encoding="utf-8")


def _branch_exists(repo_root: Path, branch: str) -> bool:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo_root,
        check=False,
        text=True,
        capture_output=True,
    )
    return completed.returncode == 0


def create_run(args: argparse.Namespace) -> Path:
    repo_root = _repo_root()
    run_dir = repo_root / ".agents" / "runs" / args.run_id
    if run_dir.exists():
        raise SystemExit(f"run directory already exists: {run_dir} (delete it or pick a new --run-id)")
    if _branch_exists(repo_root, args.branch):
        raise SystemExit(f"branch already exists: {args.branch} (delete it with `git branch -D` or pick a new --branch)")
    worktree_path = repo_root / args.worktree
    if worktree_path.exists():
        raise SystemExit(f"worktree path already exists: {worktree_path} (remove it with `git worktree remove` first)")
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest_path = run_dir / "manifest.json"
    manifest = {
        "run_id": args.run_id,
        "task_id": args.task_id,
        "objective": args.objective,
        "assigned_agent": args.agent,
        "branch": args.branch,
        "worktree_path": args.worktree,
        "allowed_paths": args.allow,
        "required_tests": args.test,
        "status": "ready",
        "scope_violation_count": 0,
    }
    write_manifest(manifest_path, manifest)
    _write_brief(run_dir, manifest)
    subprocess.run(["git", "worktree", "add", "-b", args.branch, str(worktree_path)], cwd=repo_root, check=True)
    active_dir = worktree_path / ".agents"
    active_dir.mkdir(parents=True, exist_ok=True)
    (active_dir / "active-manifest").write_text(str(manifest_path.resolve()), encoding="utf-8")
    return manifest_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--objective", required=True)
    parser.add_argument("--agent", required=True)
    parser.add_argument("--branch", required=True)
    parser.add_argument("--worktree", required=True)
    parser.add_argument("--allow", action="append", required=True)
    parser.add_argument("--test", action="append", required=True)
    args = parser.parse_args()
    print(create_run(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
