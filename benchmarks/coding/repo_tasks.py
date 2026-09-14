"""Large-repo benchmark tasks: the CopeNet checkout itself as the workspace.

The fixture tasks in `tasks.py` measure the harness on a repository the model
can hold in its head. This family measures what changes when it cannot: a
where-is-it question that spans frontend, RPC, orchestrator and store; a trace
of one event across five layers; a deliberately broad question that tempts a
repo-wide search; a real fix gated by the project's own pytest; and a two-turn
continuation whose first turn is heavy enough to push the replay into the
receipt path.

Every task runs in a detached `git worktree` of this checkout under a temp
directory (see `run.prepare_workspace`), never in the real tree, and the graders
run pytest against the worktree's own `src` via PYTHONPATH.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from benchmarks.coding.tasks import (
    Check,
    GradeContext,
    Task,
    answer_cites_line,
    answer_mentions,
    changed_files,
    changes_within,
    file_matches,
    line_of,
    paths_unchanged,
    replace_once,
    verification_after_last_edit,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

ENVIRONMENT_NOTE = (
    "Environment: this is a git worktree of the CopeNet repository. `python` on PATH already has the "
    "project's dependencies and PYTHONPATH points at this checkout's `src`, so `python -m pytest <paths>` "
    "works directly. Do not run `uv sync`, `uv run`, or `npm install`."
)


def pytest_passes(workdir: Path, *paths: str, timeout: float = 300.0) -> Check:
    """Run the worktree's own tests with the worktree's own source on the path."""
    env = {**os.environ, "PYTHONPATH": str(workdir / "src")}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *paths],
        cwd=workdir, capture_output=True, text=True, timeout=timeout, env=env,
    )
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-2:]
    return Check(f"pytest passes: {' '.join(paths)}", proc.returncode == 0, " | ".join(tail))


def _analysis(ctx: GradeContext, index: int = -1) -> dict:
    try:
        return ctx.analyses[index] or {}
    except IndexError:
        return {}


def search_discipline(analysis: dict, *, max_dumps: int = 1) -> Check:
    dumps = (analysis.get("reads") or {}).get("searchDumps") or []
    detail = ", ".join(f"step {d.get('step')} /{d.get('pattern')}/ → {d.get('totalMatches')} matches" for d in dumps[:4]) or "no search over 200 matches"
    return Check(f"at most {max_dumps} search returned more than 200 matches", len(dumps) <= max_dumps, detail)


def no_redundant_reads(analysis: dict, *, allowed: int = 1) -> Check:
    count = int((analysis.get("reads") or {}).get("redundantReadCount") or 0)
    return Check(f"redundant reads ≤ {allowed}", count <= allowed, f"redundant reads: {count}, distinct files: {(analysis.get('reads') or {}).get('distinctFilesRead')}")


def no_changes(workdir: Path) -> Check:
    changed = changed_files(workdir)
    return Check("no files changed", not changed, ", ".join(changed) or "clean")


# ---------------------------------------------------------------------------
# Read-only tasks
# ---------------------------------------------------------------------------


def grade_repo_where_is_it(workdir: Path, ctx: GradeContext) -> list[Check]:
    text = ctx.final_text
    analysis = _analysis(ctx)
    return [
        no_changes(workdir),
        answer_mentions(text, ["ObservabilityPage", "observability.settings.update"], label="names the frontend component and the RPC method"),
        answer_mentions(text, ["handle_observability_settings_update", "update_observability_settings"], label="names the host handler and the orchestrator method"),
        answer_mentions(text, ["observability.json", "update_settings"], label="names the settings file and the store method"),
        answer_mentions(text, ["run_admission", "debug_capture"], label="finds where a run reads the flag"),
        answer_cites_line(text, "src/copenet/host/rpc_observability.py", line_of(workdir, "src/copenet/host/rpc_observability.py", "def handle_observability_settings_update"), label="cites the handler's line"),
        answer_cites_line(text, "src/copenet/core/orchestrator/run_admission.py", line_of(workdir, "src/copenet/core/orchestrator/run_admission.py", "debug=trace_settings.debug_capture"), label="cites the line where the writer receives the flag"),
        search_discipline(analysis),
        no_redundant_reads(analysis),
    ]


def grade_repo_trace_event(workdir: Path, ctx: GradeContext) -> list[Check]:
    text = ctx.final_text
    analysis = _analysis(ctx)
    return [
        no_changes(workdir),
        answer_mentions(text, ["token_usage_event", "base.py"], label="finds the provider-side constructor"),
        answer_mentions(text, ["codex_responses.py", "claude_cli.py"], label="names both providers that emit it"),
        answer_mentions(text, ["tool_loop_common", "tool_loop_responses"], label="follows it through the tool loop"),
        answer_mentions(text, ["consume_metadata", "run_events.py", "provider_usage_reported"], label="finds the consumer that writes the trace row"),
        answer_mentions(text, ["summarize_token_usage", "run_finalization"], label="connects it to the run record's tokenUsage"),
        answer_cites_line(text, "src/copenet/providers/base.py", line_of(workdir, "src/copenet/providers/base.py", "def token_usage_event"), label="cites token_usage_event's line"),
        answer_cites_line(text, "src/copenet/core/orchestrator/run_events.py", line_of(workdir, "src/copenet/core/orchestrator/run_events.py", 'record("provider_usage_reported"'), label="cites the trace record line"),
        answer_cites_line(text, "src/copenet/core/orchestrator/token_usage.py", line_of(workdir, "src/copenet/core/orchestrator/token_usage.py", "def summarize_token_usage"), label="cites summarize_token_usage's line"),
        search_discipline(analysis),
        no_redundant_reads(analysis),
    ]


def grade_repo_broad_question(workdir: Path, ctx: GradeContext) -> list[Check]:
    text = ctx.final_text
    analysis = _analysis(ctx)
    return [
        no_changes(workdir),
        answer_mentions(text, ["assert_session_binding", "session_store.py"], label="names the store method that enforces the lock"),
        answer_mentions(text, ["run_admission", "resolve_or_create"], label="names the admission path that calls it"),
        answer_mentions(text, ["policy_for_task_mode"], label="mentions the downstream Access gate"),
        answer_mentions(text, ["useAppStore", "ChatWorkspace"], label="names the frontend state and surface that gate the pickers"),
        answer_mentions(text, ["test_session_store"], label="names the test that pins it"),
        answer_cites_line(text, "src/copenet/core/sessions/session_store.py", line_of(workdir, "src/copenet/core/sessions/session_store.py", "def assert_session_binding"), label="cites assert_session_binding's line"),
        answer_cites_line(text, "src/copenet/core/orchestrator/run_admission.py", line_of(workdir, "src/copenet/core/orchestrator/run_admission.py", "assert_session_binding("), label="cites the admission call site"),
        search_discipline(analysis, max_dumps=1),
        no_redundant_reads(analysis),
    ]


# ---------------------------------------------------------------------------
# Editing tasks (seeded defects in real modules, gated by the project's tests)
# ---------------------------------------------------------------------------

CHANGE_LEDGER = "src/copenet/core/sessions/change_ledger.py"
REPLAY_RECEIPTS = "src/copenet/core/harness/replay_receipts.py"


def seed_repo_fix_gated(workdir: Path) -> None:
    # The folded per-file state keeps the FIRST digest instead of the latest one,
    # so a file edited twice in a session reads as "CHANGED ON DISK" forever.
    replace_once(
        workdir,
        CHANGE_LEDGER,
        '        state["digest"] = entry.digest_after\n',
        '        if not state["digest"]:\n            state["digest"] = entry.digest_after\n',
    )


def grade_repo_fix_gated(workdir: Path, ctx: GradeContext) -> list[Check]:
    analysis = _analysis(ctx)
    return [
        pytest_passes(workdir, "tests/unit/test_change_ledger.py", "tests/integration/test_change_ledger_turns.py"),
        paths_unchanged(workdir, ("tests/",)),
        changes_within(workdir, {CHANGE_LEDGER}),
        file_matches(workdir, CHANGE_LEDGER, r'if not state\["digest"\]', expect=False, label="first-digest guard removed"),
        file_matches(workdir, CHANGE_LEDGER, r'^\s+state\["digest"\] = entry\.digest_after$', expect=True, label="latest digest is the one kept"),
        Check("ran the tests at least once", (analysis.get("verification") or {}).get("testRuns", 0) >= 1, f"test runs: {(analysis.get('verification') or {}).get('testRuns', 0)}"),
        verification_after_last_edit(analysis),
        search_discipline(analysis),
    ]


def seed_repo_two_turn(workdir: Path) -> None:
    # Bug 1: failed calls lose their verbatim guarantee and get receipted like reads.
    replace_once(workdir, REPLAY_RECEIPTS, '    return tool_execution.get("ok") is False\n', "    return False\n")
    # Bug 2: the shell receipt forgets the exit code.
    replace_once(workdir, REPLAY_RECEIPTS, '        receipt["exitCode"] = data.get("exitCode")\n', "")


def grade_repo_two_turn(workdir: Path, ctx: GradeContext) -> list[Check]:
    turn2 = _analysis(ctx, 1) if len(ctx.analyses) >= 2 else {}
    receipts = (turn2.get("header") or {}).get("replayReceipts") or {}
    return [
        pytest_passes(workdir, "tests/unit/test_replay_receipts.py", "tests/integration/test_replay_receipts_turns.py"),
        paths_unchanged(workdir, ("tests/",)),
        changes_within(workdir, {REPLAY_RECEIPTS}),
        file_matches(workdir, REPLAY_RECEIPTS, r'return tool_execution\.get\("ok"\) is False', expect=True, label="failures are verbatim again"),
        file_matches(workdir, REPLAY_RECEIPTS, r'receipt\["exitCode"\]', expect=True, label="shell receipt carries the exit code again"),
        answer_mentions(ctx.final_text, ["replay_receipts.py", "is_verbatim", "exitCode"], label="final answer names the file and both changes"),
        Check("turn 2 received the change ledger from turn 1", bool((turn2.get("changeLedger") or {}).get("injected")), f"ledger: {turn2.get('changeLedger')}"),
        Check("no stale-digest errors in turn 2", (turn2.get("edits") or {}).get("staleDigestErrors", 0) == 0, f"stale digest errors: {(turn2.get('edits') or {}).get('staleDigestErrors', 0)}"),
        Check(
            "turn 2 replay was shaped by receipts (informational)",
            True,
            f"receiptTurns={receipts.get('receiptTurns')} receiptedOutputs={receipts.get('receiptedOutputs')} "
            f"replayedChars={receipts.get('replayedChars')} verbatimChars={receipts.get('verbatimChars')}",
        ),
        verification_after_last_edit(turn2, label="turn 2 ran a verification command after its last edit") if turn2.get("edits", {}).get("mutations") else verification_after_last_edit(_analysis(ctx, 0), label="turn 1 ran a verification command after its last edit"),
    ]


REPO_TASKS: list[Task] = [
    Task(
        id="repo-where-is-it",
        title="Large repo: trace one operator control across four layers",
        capability="answer a where-is-it question that spans frontend, RPC, orchestrator and store with precise citations",
        failure_modes=["repo-wide search dumps", "stopping at the first layer", "citing files never opened", "re-reading the same file"],
        workspace="repo",
        access=None,
        turns=[
            "In the Observability section of the UI there is a Debug capture toggle. Trace it end to end: the "
            "frontend component that handles the click and the RPC method it calls, the host handler for that "
            "method, the orchestrator method it calls, where the setting is persisted (the file name on disk), "
            "and where a run later reads that setting to decide whether debug-tier trace rows are written. Cite "
            "a file path with a line number for every hop. Do not modify any files.\n\n" + ENVIRONMENT_NOTE
        ],
        grade=grade_repo_where_is_it,
        allowed_changes=set(),
    ),
    Task(
        id="repo-trace-event",
        title="Large repo: follow one event from provider to durable record",
        capability="explain a cross-layer data path (provider → tool loop → orchestrator → trace + run record) with citations",
        failure_modes=["explaining from names without opening the files", "missing the re-yield in the tool loop", "broad searches for a specific string"],
        workspace="repo",
        access=None,
        turns=[
            "Run traces contain `provider_usage_reported` rows. Explain the complete path of one of those rows: "
            "where a provider builds the token-usage event (and which two providers emit it), how it travels "
            "through the harness tool loop, which orchestrator function consumes it and writes the trace row, "
            "and how the run record's `tokenUsage` total is produced from the same data at finalization. Cite a "
            "file path with a line number for every hop. Do not modify any files.\n\n" + ENVIRONMENT_NOTE
        ],
        grade=grade_repo_trace_event,
        allowed_changes=set(),
    ),
    Task(
        id="repo-broad-question",
        title="Large repo: a deliberately broad question that tempts a repo-wide search",
        capability="narrow a vague question to the load-bearing code instead of dumping every match for a common word",
        failure_modes=["rg for 'lock' across the repo", "listing dozens of incidental files", "no citations"],
        workspace="repo",
        access=None,
        turns=[
            "Give me a complete map of how the session lock works: after a session's first send, provider, "
            "profile, persona and workspace are locked while model and Access stay changeable. I want every "
            "backend function on the path from `chat.send` to the session store that enforces or reconciles "
            "that binding, the downstream gate that keeps a mid-session Access change from over-granting, the "
            "frontend state and component that reflect the locked state to the operator, and the test file "
            "that pins the store behavior. Cite file paths with line numbers. Do not modify any files.\n\n" + ENVIRONMENT_NOTE
        ],
        grade=grade_repo_broad_question,
        allowed_changes=set(),
    ),
    Task(
        id="repo-fix-gated",
        title="Large repo: real fix gated by the project's own tests",
        capability="locate a one-line defect in a real module from a product symptom and prove the fix with the project's pytest",
        failure_modes=["editing the test", "fixing the symptom in the renderer instead of the fold", "declaring done without running the integration test"],
        workspace="repo",
        seed=seed_repo_fix_gated,
        turns=[
            "Bug report: the change ledger that CopeNet appends to an agent's next turn says a file has "
            "'CHANGED ON DISK since your last edit' whenever the agent edited that file more than once in the "
            "session, even though nothing else touched it. `python -m pytest tests/unit/test_change_ledger.py` "
            "has a failing test for this. Find the root cause and fix it in the library code, not in the tests. "
            "Then run that file and tests/integration/test_change_ledger_turns.py and report the result.\n\n" + ENVIRONMENT_NOTE
        ],
        grade=grade_repo_fix_gated,
        allowed_changes={CHANGE_LEDGER},
        protected=("tests/",),
    ),
    Task(
        id="repo-two-turn",
        title="Large repo: two turns in one real module",
        capability="carry the first turn's edits into a second turn on a large repo without going stale or re-deriving",
        failure_modes=["stale edit after replay", "re-reading everything from turn 1", "misreporting which files changed"],
        workspace="repo",
        seed=seed_repo_two_turn,
        turns=[
            "`python -m pytest tests/unit/test_replay_receipts.py::test_edits_and_failures_never_become_receipts` "
            "fails: a failed tool call from an older turn is being replayed as a receipt instead of verbatim. Find "
            "the cause in the library code, fix it there (not in the tests), and re-run that test file.\n\n" + ENVIRONMENT_NOTE,
            "There is also a failing shell-receipt test in the same file "
            "(`test_shell_receipt_keeps_command_exit_code_and_head_tail`). Fix it if you have not already, run the "
            "whole file plus tests/integration/test_replay_receipts_turns.py, and then tell me exactly which files "
            "you changed across both turns and what each change was.",
        ],
        grade=grade_repo_two_turn,
        allowed_changes={REPLAY_RECEIPTS},
        protected=("tests/",),
    ),
]
