#!/usr/bin/env python3
"""Project gate: unused imports, stray prints, then the test suite.

Gates run in order and the script stops at the first one that fails, printing
what failed and exiting non-zero. `python scripts/check.py` exiting 0 is the
project's definition of "green".
"""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "ledgerly"
PRINT_ALLOWED = {"cli.py"}


def _imported_names(tree: ast.Module) -> dict[str, int]:
    names: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names[(alias.asname or alias.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names[alias.asname or alias.name] = node.lineno
    return names


def _used_names(tree: ast.Module) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used.add(base.id)
    exported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets):
            if isinstance(node.value, (ast.List, ast.Tuple)):
                exported = {elt.value for elt in node.value.elts if isinstance(elt, ast.Constant)}
    return used | exported


def gate_unused_imports() -> list[str]:
    problems: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        used = _used_names(tree)
        for name, lineno in _imported_names(tree).items():
            if name == "annotations":
                continue
            if name not in used:
                problems.append(f"{path.relative_to(ROOT)}:{lineno}: unused import {name!r}")
    return problems


def gate_no_prints() -> list[str]:
    problems: list[str] = []
    for path in sorted(PACKAGE.glob("*.py")):
        if path.name in PRINT_ALLOWED:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                problems.append(f"{path.relative_to(ROOT)}:{node.lineno}: print() in library module")
    return problems


def gate_tests() -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return []
    tail = (proc.stderr or proc.stdout).strip().splitlines()[-25:]
    return ["test suite failed:"] + [f"  {line}" for line in tail]


GATES = (
    ("unused-imports", gate_unused_imports),
    ("no-prints", gate_no_prints),
    ("tests", gate_tests),
)


def main() -> int:
    for name, gate in GATES:
        problems = gate()
        if problems:
            print(f"[check] {name}: FAIL")
            for line in problems:
                print(line)
            return 1
        print(f"[check] {name}: ok")
    print("[check] all gates passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
