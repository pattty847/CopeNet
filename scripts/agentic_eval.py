#!/usr/bin/env python
"""Agentic capability eval — can the model actually BUILD, not just render?

Runs gpt-5.5 (or any provider/model) through realistic coding tasks in a
full-access scratch workspace, then independently checks the resulting files /
command output. Each task proves a capability: create a file, fix a bug, build
a module + tests, refactor across files, read→derive→write.

This is a LIVE eval (real API, real tool execution) — like
scripts/live_probe_matrix.py, not part of the deterministic pytest suite. It
spends provider quota, so run it deliberately.

Usage:
    uv run python scripts/agentic_eval.py
    uv run python scripts/agentic_eval.py --provider openai-codex --model gpt-5.5
    uv run python scripts/agentic_eval.py --only build_module_and_test
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from copenet.core.orchestrator import ChatSendRequest, Orchestrator

# A check returns (passed, detail).
Check = Callable[[Path], "tuple[bool, str]"]


# ---------------------------------------------------------------------------
# Check helpers — independent verification of the workspace AFTER the model runs
# ---------------------------------------------------------------------------


def file_exists(name: str) -> Check:
    def check(workdir: Path) -> tuple[bool, str]:
        ok = (workdir / name).is_file()
        return ok, f"{name} {'exists' if ok else 'MISSING'}"
    return check


def file_contains(name: str, needle: str) -> Check:
    def check(workdir: Path) -> tuple[bool, str]:
        path = workdir / name
        if not path.is_file():
            return False, f"{name} missing"
        text = path.read_text(encoding="utf-8", errors="replace")
        ok = needle in text
        return ok, f"{name} {'contains' if ok else 'MISSING'} {needle!r}"
    return check


def file_absent_text(name: str, needle: str) -> Check:
    def check(workdir: Path) -> tuple[bool, str]:
        path = workdir / name
        if not path.is_file():
            return False, f"{name} missing"
        text = path.read_text(encoding="utf-8", errors="replace")
        ok = needle not in text
        return ok, f"{name} {'no longer has' if ok else 'STILL HAS'} {needle!r}"
    return check


def file_absent_regex(name: str, pattern: str) -> Check:
    import re

    compiled = re.compile(pattern)

    def check(workdir: Path) -> tuple[bool, str]:
        path = workdir / name
        if not path.is_file():
            return False, f"{name} missing"
        text = path.read_text(encoding="utf-8", errors="replace")
        ok = compiled.search(text) is None
        return ok, f"{name} {'no longer matches' if ok else 'STILL MATCHES'} /{pattern}/"
    return check


def runs_with_output(argv: list[str], expected_substr: str, timeout: float = 20.0) -> Check:
    def check(workdir: Path) -> tuple[bool, str]:
        try:
            proc = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            return False, f"`{' '.join(argv)}` raised {exc}"
        out = (proc.stdout or "") + (proc.stderr or "")
        ok = expected_substr in out
        preview = out.strip().splitlines()[:1]
        return ok, f"`{' '.join(argv)}` -> {'found' if ok else 'MISSING'} {expected_substr!r} (out: {preview})"
    return check


def command_succeeds(argv: list[str], timeout: float = 20.0) -> Check:
    def check(workdir: Path) -> tuple[bool, str]:
        try:
            proc = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=timeout)
        except Exception as exc:  # noqa: BLE001
            return False, f"`{' '.join(argv)}` raised {exc}"
        ok = proc.returncode == 0
        return ok, f"`{' '.join(argv)}` exit={proc.returncode}"
    return check


# ---------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------


@dataclass
class Scenario:
    id: str
    title: str
    prompt: str
    checks: list[Check]
    setup: Callable[[Path], None] = field(default=lambda _d: None)


def _seed(files: dict[str, str]) -> Callable[[Path], None]:
    def setup(workdir: Path) -> None:
        for name, content in files.items():
            target = workdir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
    return setup


SCENARIOS: list[Scenario] = [
    Scenario(
        id="create_file",
        title="Create a runnable file from scratch",
        prompt=(
            "Create a file named hello.py in the current working directory that, when run "
            "with `python hello.py`, prints exactly this line:\nHello, CopeNet"
        ),
        checks=[
            file_exists("hello.py"),
            runs_with_output(["python", "hello.py"], "Hello, CopeNet"),
        ],
    ),
    Scenario(
        id="fix_bug",
        title="Find and fix a bug in an existing file",
        prompt=(
            "There is a bug in math_ops.py: the add() function subtracts instead of adding. "
            "Read the file, fix the bug so add(a, b) returns a + b, and leave everything else intact."
        ),
        setup=_seed({"math_ops.py": "def add(a, b):\n    return a - b\n\n\ndef mul(a, b):\n    return a * b\n"}),
        checks=[
            file_contains("math_ops.py", "a + b"),
            file_absent_text("math_ops.py", "a - b"),
            runs_with_output(["python", "-c", "import math_ops; print(math_ops.add(2, 3))"], "5"),
        ],
    ),
    Scenario(
        id="build_module_and_test",
        title="Build a module + tests and make them pass",
        prompt=(
            "Create two files in the current directory:\n"
            "1) calc.py with two functions: add(a, b) returning a + b, and multiply(a, b) returning a * b.\n"
            "2) test_calc.py that imports from calc and uses plain `assert` statements to verify "
            "add(2, 3) == 5 and multiply(2, 3) == 6, and prints 'ok' at the end.\n"
            "Then run `python test_calc.py` and make sure it passes (exit code 0)."
        ),
        checks=[
            file_exists("calc.py"),
            file_exists("test_calc.py"),
            command_succeeds(["python", "test_calc.py"]),
            runs_with_output(["python", "-c", "import calc; print(calc.add(2,3), calc.multiply(2,3))"], "5 6"),
        ],
    ),
    Scenario(
        id="refactor_rename",
        title="Rename a function across multiple files",
        prompt=(
            "Across the Python files in this directory, the function `greet` is defined in greeter.py "
            "and used in app.py. Rename it from `greet` to `welcome` everywhere — its definition and all "
            "call sites — so the code still works. Do not change its behavior."
        ),
        setup=_seed({
            "greeter.py": "def greet(name):\n    return f'Hi, {name}'\n",
            "app.py": "from greeter import greet\n\n\ndef main():\n    print(greet('CopeNet'))\n\n\nif __name__ == '__main__':\n    main()\n",
        }),
        checks=[
            file_contains("greeter.py", "def welcome"),
            # word-boundary so "greeter" (the module name) doesn't count as "greet"
            file_absent_regex("greeter.py", r"\bgreet\b"),
            file_absent_regex("app.py", r"\bgreet\b"),
            runs_with_output(["python", "app.py"], "Hi, CopeNet"),
        ],
    ),
    Scenario(
        id="read_derive_write",
        title="Read a file, derive a fact, write a new file",
        prompt=(
            "Read data.txt in the current directory. Count how many lines it has, and write a new file "
            "named summary.txt whose only content is that number (just the integer, nothing else)."
        ),
        setup=_seed({"data.txt": "alpha\nbeta\ngamma\ndelta\nepsilon\n"}),
        checks=[
            file_exists("summary.txt"),
            file_contains("summary.txt", "5"),
        ],
    ),
    Scenario(
        id="debug_failing_test",
        title="Debug a failing test (read test, find bug, make it green)",
        prompt=(
            "The tests in test_stack.py are failing. Run them to see the failure, then find and fix the "
            "bug in stack.py so the tests pass. Do not modify test_stack.py — only fix stack.py. "
            "Re-run the tests to confirm they pass."
        ),
        setup=_seed({
            "stack.py": (
                "class Stack:\n"
                "    def __init__(self):\n"
                "        self._items = []\n\n"
                "    def push(self, x):\n"
                "        self._items.append(x)\n\n"
                "    def pop(self):\n"
                "        return self._items.pop(0)  # bug: pops the oldest, not the newest\n\n"
                "    def is_empty(self):\n"
                "        return len(self._items) == 0\n"
            ),
            "test_stack.py": (
                "from stack import Stack\n\n"
                "s = Stack()\n"
                "s.push(1)\n"
                "s.push(2)\n"
                "s.push(3)\n"
                "assert s.pop() == 3, 'expected LIFO order (newest first)'\n"
                "assert s.pop() == 2\n"
                "assert s.pop() == 1\n"
                "assert s.is_empty()\n"
                "print('ok')\n"
            ),
        }),
        checks=[
            command_succeeds(["python", "test_stack.py"]),
            file_absent_regex("stack.py", r"pop\(0\)"),
        ],
    ),
    Scenario(
        id="build_cli_tool",
        title="Build a CLI tool that takes an argument",
        prompt=(
            "Create wordcount.py that takes a single filename as a command-line argument and prints just "
            "the number of whitespace-separated words in that file (one integer, nothing else). "
            "For example, `python wordcount.py sample.txt` should print the word count of sample.txt."
        ),
        setup=_seed({"sample.txt": "one two three four five six seven\n"}),
        checks=[
            file_exists("wordcount.py"),
            runs_with_output(["python", "wordcount.py", "sample.txt"], "7"),
        ],
    ),
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


@dataclass
class ScenarioResult:
    id: str
    title: str
    passed: bool
    check_results: list[tuple[bool, str]]
    run_status: str
    tool_calls: int
    error: str | None
    elapsed_sec: float


async def run_scenario(orch: Orchestrator, scenario: Scenario, *, provider: str, model: str) -> ScenarioResult:
    workdir = Path(tempfile.mkdtemp(prefix=f"copenet-eval-{scenario.id}-"))
    scenario.setup(workdir)
    session_key = f"eval-{scenario.id}-{int(time.time())}"
    started = time.time()
    tool_calls = 0
    run_status = "ok"
    error: str | None = None

    async def emit(payload: dict) -> None:
        nonlocal tool_calls, error
        if payload.get("state") == "tool_called":
            tool_calls += 1
        elif payload.get("state") == "error":
            err = payload.get("errorMessage") or payload.get("error")
            if err:
                error = str(err)

    try:
        result = await orch.send_chat(
            ChatSendRequest(
                session_key=session_key,
                message=scenario.prompt,
                provider=provider,
                model=model,
                task_prompt_id="full-access",
                workspace_root=str(workdir),
                allow_tools=True,
            ),
            emit=emit,
        )
        run_status = str(result.get("status") or "ok")
        if result.get("summary") and run_status != "ok":
            error = error or str(result.get("summary"))
    except Exception as exc:  # noqa: BLE001
        run_status = "exception"
        error = f"{type(exc).__name__}: {exc}"

    check_results = [check(workdir) for check in scenario.checks]
    passed = run_status == "ok" and all(ok for ok, _ in check_results)
    return ScenarioResult(
        id=scenario.id,
        title=scenario.title,
        passed=passed,
        check_results=check_results,
        run_status=run_status,
        tool_calls=tool_calls,
        error=error,
        elapsed_sec=round(time.time() - started, 1),
    )


def print_result(res: ScenarioResult) -> None:
    badge = "PASS" if res.passed else "FAIL"
    print(f"\n[{badge}] {res.id} — {res.title}")
    print(f"       run={res.run_status}  tools={res.tool_calls}  {res.elapsed_sec}s")
    if res.error:
        print(f"       error: {res.error[:200]}")
    for ok, detail in res.check_results:
        print(f"         {'✓' if ok else '✗'} {detail}")


async def main_async(args: argparse.Namespace) -> int:
    scenarios = SCENARIOS
    if args.only:
        scenarios = [s for s in SCENARIOS if s.id in set(args.only)]
        if not scenarios:
            print(f"No scenarios match {args.only}. Available: {[s.id for s in SCENARIOS]}")
            return 2

    print("=" * 64)
    print(f"Agentic capability eval — {args.provider} / {args.model}")
    print(f"{len(scenarios)} scenario(s)")
    print("=" * 64)

    orch = Orchestrator()
    results: list[ScenarioResult] = []
    for scenario in scenarios:
        print(f"\n▶ {scenario.id} …", flush=True)
        res = await run_scenario(orch, scenario, provider=args.provider, model=args.model)
        print_result(res)
        results.append(res)

    passed = sum(1 for r in results if r.passed)
    print("\n" + "=" * 64)
    print(f"SCORE: {passed}/{len(results)} passed")
    for r in results:
        print(f"  {'✓' if r.passed else '✗'} {r.id}")
    print("=" * 64)

    if args.out:
        Path(args.out).write_text(
            json.dumps(
                {
                    "ranAtEpoch": int(time.time()),
                    "provider": args.provider,
                    "model": args.model,
                    "score": f"{passed}/{len(results)}",
                    "results": [
                        {
                            "id": r.id,
                            "title": r.title,
                            "passed": r.passed,
                            "runStatus": r.run_status,
                            "toolCalls": r.tool_calls,
                            "elapsedSec": r.elapsed_sec,
                            "error": r.error,
                            "checks": [{"ok": ok, "detail": d} for ok, d in r.check_results],
                        }
                        for r in results
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"Wrote {args.out}")
    return 0 if passed == len(results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Agentic capability eval for CopeNet")
    parser.add_argument("--provider", default="openai-codex")
    parser.add_argument("--model", default="gpt-5.5")
    parser.add_argument("--only", nargs="*", help="Scenario id(s) to run")
    parser.add_argument("--out", default="docs/investigations/agentic-eval/last-run.json")
    args = parser.parse_args()
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
