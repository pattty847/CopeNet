#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import stat
import subprocess
from pathlib import Path


def _git_path(worktree: Path, hook_name: str) -> Path:
    completed = subprocess.run(
        ["git", "rev-parse", "--git-path", f"hooks/{hook_name}"],
        cwd=worktree,
        check=True,
        text=True,
        capture_output=True,
    )
    return (worktree / completed.stdout.strip()).resolve()


def install_hooks(worktree: str | Path) -> list[Path]:
    worktree_path = Path(worktree).resolve()
    hook_source_dir = Path(__file__).resolve().parents[1] / "hooks"
    installed: list[Path] = []
    for hook_name in ("pre-commit", "commit-msg"):
        source = hook_source_dir / hook_name
        target = _git_path(worktree_path, hook_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        installed.append(target)
    return installed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worktree", required=True)
    args = parser.parse_args()
    for path in install_hooks(args.worktree):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
