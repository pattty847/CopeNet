#!/usr/bin/env python3
"""Run objective CopeNet permission probes."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from copenet.probes.permission_matrix import run_permission_matrix


def _parse_modes(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _print_table(rows: list) -> None:
    print(f"{'mode':14s} {'probe':26s} {'ok':5s} {'policy':18s} {'pass':5s} summary")
    print("-" * 112)
    for row in rows:
        mark = "PASS" if row.passed else "FAIL"
        ok = "true" if row.ok else "false"
        print(
            f"{row.task_mode[:14]:14s} "
            f"{row.probe[:26]:26s} "
            f"{ok:5s} "
            f"{row.policy_decision[:18]:18s} "
            f"{mark:5s} "
            f"{row.summary}"
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Run direct CopeNet tool permission probes.")
    parser.add_argument("--task-modes", default="none,full-access", help="Comma-separated task modes to probe.")
    parser.add_argument("--workspace", default=None, help="Optional scratch workspace. Defaults to a temporary directory.")
    parser.add_argument("--json", action="store_true", help="Print JSON rows.")
    args = parser.parse_args()

    rows = await run_permission_matrix(
        task_modes=_parse_modes(args.task_modes),
        workspace=Path(args.workspace).resolve() if args.workspace else None,
    )
    if args.json:
        print(json.dumps({"rows": [row.to_json() for row in rows]}, indent=2, sort_keys=True))
    else:
        _print_table(rows)
    if not all(row.passed for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())

