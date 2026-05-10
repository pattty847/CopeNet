#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from mao_manifest import load_manifest, read_active_manifest_path


def _repo_root() -> Path:
    completed = subprocess.run(["git", "rev-parse", "--show-toplevel"], check=True, text=True, capture_output=True)
    return Path(completed.stdout.strip())


def main(argv: list[str] | None = None) -> int:
    args = argv or sys.argv[1:]
    if not args:
        sys.stderr.write("commit-msg hook requires the commit message path\n")
        return 1
    repo_root = _repo_root()
    manifest_path = read_active_manifest_path(repo_root)
    if manifest_path is None:
        return 0
    manifest = load_manifest(manifest_path)
    message_path = Path(args[0])
    first_line = message_path.read_text(encoding="utf-8").splitlines()[0].strip()
    required_prefix = f"[{manifest['task_id']}]"
    if first_line.startswith(required_prefix):
        return 0
    sys.stderr.write(f"Commit message must start with {required_prefix}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
