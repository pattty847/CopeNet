"""Run the coding-agent benchmark through the real CopeNet orchestrator.

    uv run python -m benchmarks.coding.run --list
    uv run python -m benchmarks.coding.run --dry-run            # seeds + graders only, no model
    uv run python -m benchmarks.coding.run --provider openai-codex --model gpt-5.5
    uv run python -m benchmarks.coding.run --only bugfix-local explore-locate

Each task gets a fresh workspace — a copy of the fixture repo for the fixture
family, or a detached `git worktree` of this checkout (HEAD) for the large-repo
family — git-initialized so the grader can diff, a fresh `bench-*` session in
the operator's real ~/.copenet store so the run shows up in Observability, and
Debug capture switched on for the duration so the trace carries full tool
arguments and result bodies. Results land under tmp/coding_bench/<timestamp>/.

Run it as `uv run --extra dev python -m benchmarks.coding.run …`: the repo
tasks' graders (and the model, through PYTHONPATH) use this interpreter's
pytest against the worktree's own `src`.

This spends provider quota and executes real tools inside the temp workspace.
The real checkout is never the workspace.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from benchmarks.coding import trace_analysis  # noqa: E402
from benchmarks.coding.catalog import TASKS, TASKS_BY_ID  # noqa: E402
from benchmarks.coding.report import aggregate_rows, render_suite_report, summary_row  # noqa: E402
from benchmarks.coding.tasks import FIXTURE_ROOT, Check, GradeContext, Task  # noqa: E402

DEFAULT_OUT = REPO_ROOT / "tmp" / "coding_bench"


def _git(workdir: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", "user.name=bench", "-c", "user.email=bench@example.invalid", *argv],
        cwd=workdir, capture_output=True, text=True, check=False,
    )


def prepare_workspace(task: Task, *, keep_root: Path | None = None, seed: bool = True) -> Path:
    base = keep_root or Path(tempfile.gettempdir())
    workdir = Path(tempfile.mkdtemp(prefix=f"copenet-bench-{task.id}-", dir=str(base)))
    if task.workspace == "repo":
        # A detached worktree of HEAD: the model can edit and run freely without
        # touching the real tree, and `git status` in it sees only its own changes.
        workdir.rmdir()
        proc = _git(REPO_ROOT, "worktree", "add", "--detach", "-q", str(workdir), "HEAD")
        if proc.returncode != 0:
            raise RuntimeError(f"git worktree add failed: {proc.stderr.strip()}")
    else:
        shutil.copytree(FIXTURE_ROOT, workdir, dirs_exist_ok=True)
        for cache in workdir.rglob("__pycache__"):
            shutil.rmtree(cache, ignore_errors=True)
        _git(workdir, "init", "-q")
    if seed:
        task.seed(workdir)
    _git(workdir, "add", "-A")
    _git(workdir, "commit", "-q", "--allow-empty", "-m", "seeded benchmark state")
    return workdir


def cleanup_workspace(task: Task, workdir: Path) -> None:
    if task.workspace == "repo":
        _git(REPO_ROOT, "worktree", "remove", "--force", str(workdir))
        _git(REPO_ROOT, "worktree", "prune")
    shutil.rmtree(workdir, ignore_errors=True)


@contextlib.contextmanager
def workspace_environment(task: Task, workdir: Path):
    """Point PYTHONPATH at the worktree's `src` for the duration of a repo task.

    Tool subprocesses inherit the process environment, so this is what makes the
    model's `python -m pytest` import the worktree's code instead of the editable
    install of the real checkout.
    """
    if task.workspace != "repo":
        yield
        return
    previous = os.environ.get("PYTHONPATH")
    os.environ["PYTHONPATH"] = str(workdir / "src")
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("PYTHONPATH", None)
        else:
            os.environ["PYTHONPATH"] = previous


def workspace_diff(workdir: Path) -> str:
    _git(workdir, "add", "-N", ".")
    return _git(workdir, "diff").stdout


def _check_rows(checks: list[Check]) -> list[dict[str, Any]]:
    return [asdict(check) for check in checks]


async def run_task(orchestrator, task: Task, *, provider: str, model: str | None, out_dir: Path, timeout_sec: float, keep: bool, repeat_index: int = 1, repeat_total: int = 1) -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    # Every repeat is a fresh session and a fresh workspace: nothing carries over
    # between runs except the model's own variance, which is what repeats measure.
    session_key = f"bench-{task.id}-{stamp}" + (f"-r{repeat_index}" if repeat_total > 1 else "")
    workdir = prepare_workspace(task)
    task_dir = out_dir / task.id / (f"run{repeat_index}" if repeat_total > 1 else "")
    task_dir.mkdir(parents=True, exist_ok=True)
    label = f" (run {repeat_index}/{repeat_total})" if repeat_total > 1 else ""
    print(f"\n▶ {task.id}{label} — {task.title}\n  session {session_key}\n  workspace {workdir}", flush=True)
    try:
        result = await _run_task_in(orchestrator, task, workdir=workdir, task_dir=task_dir, session_key=session_key, provider=provider, model=model, timeout_sec=timeout_sec, keep=keep)
        result["repeat"] = repeat_index
        (task_dir / "result.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
        return result
    except BaseException:
        if not keep:
            cleanup_workspace(task, workdir)
        raise


async def _run_task_in(orchestrator, task: Task, *, workdir: Path, task_dir: Path, session_key: str, provider: str, model: str | None, timeout_sec: float, keep: bool) -> dict[str, Any]:
    from copenet.core.orchestrator.requests import ChatSendRequest

    turns: list[dict[str, Any]] = []
    final_texts: list[str] = []
    analyses: list[dict[str, Any]] = []
    for turn_index, prompt in enumerate(task.turns, start=1):
        run_id = f"{session_key}-t{turn_index}"
        events: list[dict[str, Any]] = []
        final_text = ""
        status = "ok"
        error = None

        async def emit(payload: dict[str, Any]) -> None:
            nonlocal final_text, error
            events.append(payload)
            state = payload.get("state")
            if state == "tool_called":
                tool = payload.get("toolCall") or {}
                print(f"    [{tool.get('toolId')}] {str(tool.get('target') or '')[:100]}", flush=True)
            elif state == "tool_result":
                tool = payload.get("toolExecution") or {}
                mark = "ok" if tool.get("ok") is not False else "FAIL"
                print(f"      -> {mark} {str(tool.get('summary') or '')[:110]}", flush=True)
            elif state == "final":
                message = payload.get("message") or {}
                final_text = str(message.get("content") or "")
            elif state == "error":
                error = str(payload.get("errorMessage") or payload.get("error") or "")

        started = time.time()
        try:
            with workspace_environment(task, workdir):
                result = await asyncio.wait_for(
                    orchestrator.send_chat(
                        ChatSendRequest(
                            session_key=session_key,
                            message=prompt,
                            idempotency_key=run_id,
                            provider=provider,
                            model=model,
                            task_prompt_id=task.access,
                            workspace_root=str(workdir),
                            allow_tools=True,
                        ),
                        emit=emit,
                    ),
                    timeout=timeout_sec,
                )
            status = str(result.get("status") or "ok")
            if status != "ok":
                error = error or str(result.get("summary") or status)
        except asyncio.TimeoutError:
            status = "timeout"
            error = f"turn exceeded {timeout_sec:.0f}s"
        except Exception as exc:  # noqa: BLE001
            status = "exception"
            error = f"{type(exc).__name__}: {exc}"
        elapsed = round(time.time() - started, 1)

        trace_path = orchestrator._observability_store.trace_path_for(run_id)
        analysis: dict[str, Any] = {}
        if trace_path.exists():
            shutil.copy(trace_path, task_dir / f"turn{turn_index}.trace.jsonl")
            try:
                analysis = trace_analysis.analyze(trace_analysis.load_rows(trace_path))
            except Exception as exc:  # noqa: BLE001
                analysis = {"error": f"analysis failed: {exc}"}
        record = orchestrator._run_store.get(session_key, run_id)
        (task_dir / f"turn{turn_index}.events.json").write_text(json.dumps(events, indent=1, default=str), encoding="utf-8")
        (task_dir / f"turn{turn_index}.final.md").write_text(final_text, encoding="utf-8")
        (task_dir / f"turn{turn_index}.analysis.json").write_text(json.dumps(analysis, indent=1, default=str), encoding="utf-8")
        if record is not None:
            (task_dir / f"turn{turn_index}.run_record.json").write_text(json.dumps(record.to_public_dict(), indent=1, default=str), encoding="utf-8")
        final_texts.append(final_text)
        analyses.append(analysis)
        turns.append({
            "turn": turn_index,
            "runId": run_id,
            "status": status,
            "error": error,
            "elapsedSec": elapsed,
            "finalChars": len(final_text),
            "tokenUsage": record.token_usage if record is not None else None,
        })
        print(f"  turn {turn_index}: {status} in {elapsed}s, {analysis.get('toolCalls', '?')} tool calls, {analysis.get('modelCalls', '?')} model calls", flush=True)
        if status != "ok":
            break

    (task_dir / "workspace.diff").write_text(workspace_diff(workdir), encoding="utf-8")
    checks = task.grade(workdir, GradeContext(final_texts=final_texts, analyses=analyses))
    passed = all(check.ok for check in checks) and all(turn["status"] == "ok" for turn in turns)
    for check in checks:
        print(f"    {'✓' if check.ok else '✗'} {check.name} — {check.detail}", flush=True)
    result = {
        "id": task.id,
        "title": task.title,
        "capability": task.capability,
        "failureModes": task.failure_modes,
        "sessionKey": session_key,
        "workspace": str(workdir),
        "passed": passed,
        "turns": turns,
        "checks": _check_rows(checks),
        "analyses": analyses,
    }
    (task_dir / "result.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
    if keep:
        if task.workspace == "repo":
            print(f"  kept worktree {workdir} — remove with: git worktree remove --force {workdir}", flush=True)
    else:
        cleanup_workspace(task, workdir)
    print(f"  {'PASS' if passed else 'FAIL'} {task.id}", flush=True)
    return result


def dry_run(tasks: list[Task]) -> int:
    """Seed each task and confirm the grader rejects the unfixed state and accepts the pristine source."""
    failures = 0
    for task in tasks:
        workdir = prepare_workspace(task)
        try:
            checks = task.grade(workdir, GradeContext(final_texts=[""], analyses=[{}]))
        finally:
            cleanup_workspace(task, workdir)
        red = [check for check in checks if not check.ok]
        print(f"{task.id:<26} seeded state → {'RED (good)' if red else 'GREEN (seed is not failing!)'}: {[c.name for c in red][:4]}")
        if not red:
            failures += 1
        # A seeded repo task must be red *because of the seed*: the same gate must be green on HEAD.
        if task.workspace == "repo" and task.seed is not Task.seed:
            pristine = prepare_workspace(task, seed=False)
            try:
                gates = [c for c in task.grade(pristine, GradeContext(final_texts=[""], analyses=[{}])) if c.name.startswith("pytest passes")]
            finally:
                cleanup_workspace(task, pristine)
            green = all(c.ok for c in gates)
            print(f"{'':<26} unseeded HEAD gate → {'GREEN (good)' if green else 'RED (gate fails without the seed!)'}: {[c.detail for c in gates if not c.ok][:1]}")
            failures += int(not green)
    # pristine fixture must pass its own gate script
    pristine = Path(tempfile.mkdtemp(prefix="copenet-bench-pristine-"))
    shutil.copytree(FIXTURE_ROOT, pristine, dirs_exist_ok=True)
    proc = subprocess.run([sys.executable, "scripts/check.py"], cwd=pristine, capture_output=True, text=True)
    print(f"pristine fixture check.py → exit {proc.returncode}")
    failures += int(proc.returncode != 0)
    shutil.rmtree(pristine, ignore_errors=True)
    return 1 if failures else 0


async def main_async(args: argparse.Namespace) -> int:
    tasks = [TASKS_BY_ID[task_id] for task_id in args.only] if args.only else list(TASKS)
    if args.dry_run:
        return dry_run(tasks)

    from copenet.core.orchestrator import Orchestrator

    orchestrator = Orchestrator()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.out) / f"{stamp}-{args.provider}-{(args.model or 'default').replace('/', '_')}"
    out_dir.mkdir(parents=True, exist_ok=True)
    previous = orchestrator._observability_store.load_settings().debug_capture
    if not args.no_debug_capture and not previous:
        orchestrator.update_observability_settings(debug_capture=True)
    print(f"Coding-agent benchmark — {args.provider} / {args.model or 'default'} — {len(tasks)} task(s) → {out_dir}")
    results: list[dict[str, Any]] = []
    try:
        # Round-robin over repeats so a slow hour or a provider hiccup lands on
        # every task's run k, not on all of one task's runs.
        for repeat_index in range(1, args.repeat + 1):
            for task in tasks:
                results.append(await run_task(orchestrator, task, provider=args.provider, model=args.model, out_dir=out_dir, timeout_sec=args.timeout_sec, keep=args.keep, repeat_index=repeat_index, repeat_total=args.repeat))
    finally:
        if not args.no_debug_capture and not previous:
            orchestrator.update_observability_settings(debug_capture=False)
    summary = {
        "ranAt": stamp,
        "provider": args.provider,
        "model": args.model,
        "repeat": args.repeat,
        "score": f"{sum(1 for r in results if r['passed'])}/{len(results)}",
        "tasks": [summary_row(r) for r in results],
        "aggregate": aggregate_rows(results),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    (out_dir / "REPORT.md").write_text(render_suite_report(summary, results), encoding="utf-8")
    print("\n" + "=" * 72)
    print(f"SCORE {summary['score']}  →  {out_dir / 'REPORT.md'}")
    if args.repeat > 1:
        for row in summary["aggregate"]:
            print(f"  {row['id']:<26} pass {row['passes']}/{row['runs']}  tools {_spread(row['toolCalls'])}  calls {_spread(row['modelCalls'])}  peak {_spread(row['peakInput'])}  billed {_spread(row['billedInput'])}  dumps {_spread(row['searchDumps'])}  failed={row['failedChecks']}")
    else:
        for row in summary["tasks"]:
            print(f"  {'✓' if row['passed'] else '✗'} {row['id']:<26} tools={row['toolCalls']} calls={row['modelCalls']} peakIn={row['peakInput']} dumps={row['searchDumps']} failed={row['failedChecks']}")
    return 0 if all(r["passed"] for r in results) else 1


def _spread(stat: dict[str, Any]) -> str:
    return f"{stat['median']} ({stat['min']}–{stat['max']})"


def main() -> int:
    parser = argparse.ArgumentParser(description="CopeNet coding-agent benchmark")
    parser.add_argument("--provider", default="openai-codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--only", nargs="*", help="task id(s)")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="seed and grade without a model; proves each task starts red")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--timeout-sec", type=float, default=900.0)
    parser.add_argument("--keep", action="store_true", help="keep temp workspaces")
    parser.add_argument("--repeat", type=int, default=1, help="run each task N times (fresh session and workspace each) and report medians")
    parser.add_argument("--no-debug-capture", action="store_true", help="do not switch Debug capture on for the run")
    args = parser.parse_args()
    if args.list:
        for task in TASKS:
            print(f"{task.id:<26} {task.workspace:<8} {task.access or 'read-only':<12} {len(task.turns)} turn(s)  {task.title}")
        return 0
    if args.repeat < 1:
        print("--repeat must be at least 1")
        return 2
    unknown = [task_id for task_id in (args.only or []) if task_id not in TASKS_BY_ID]
    if unknown:
        print(f"unknown task id(s): {unknown}; available: {list(TASKS_BY_ID)}")
        return 2
    try:
        return asyncio.run(main_async(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
