"""Coding-agent benchmark tasks over the `ledgerly` fixture repo.

Each task is the same realistic little repository with one deliberate defect or
gap seeded into it, a prompt the operator would plausibly type, and a grader
that checks the workspace independently of anything the model claimed. The
tasks are chosen to exercise harness behavior — exploration, verification,
recovery, state tracking across edits and turns — not to test whether the model
knows Python.

A task's `access` is the Access level the session runs under: `full-access`
for anything that edits, `None` (read-only default) for pure exploration so
the same task can run against local models that never get write authority.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Callable

BENCH_ROOT = Path(__file__).resolve().parent
FIXTURE_ROOT = BENCH_ROOT / "fixture" / "ledgerly"
HIDDEN_ROOT = BENCH_ROOT / "hidden"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


@dataclass
class GradeContext:
    """What the grader may look at besides the workspace."""

    final_texts: list[str] = field(default_factory=list)
    analyses: list[dict] = field(default_factory=list)

    @property
    def final_text(self) -> str:
        return self.final_texts[-1] if self.final_texts else ""


Grader = Callable[[Path, GradeContext], list[Check]]
Seeder = Callable[[Path], None]


@dataclass
class Task:
    id: str
    title: str
    capability: str
    failure_modes: list[str]
    turns: list[str]
    grade: Grader
    seed: Seeder = lambda _workdir: None
    access: str | None = "full-access"
    # Files the task legitimately touches; anything else changed is flagged.
    allowed_changes: set[str] | None = None
    # Path prefixes that must be byte-identical to the seeded state.
    protected: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Seeding helpers
# ---------------------------------------------------------------------------


def replace_once(workdir: Path, relative: str, old: str, new: str) -> None:
    path = workdir / relative
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"seed for {relative} expected exactly one occurrence of {old!r}, found {text.count(old)}")
    path.write_text(text.replace(old, new), encoding="utf-8")


# ---------------------------------------------------------------------------
# Grading helpers — every check is an independent observation of the workspace
# ---------------------------------------------------------------------------


def _run(argv: list[str], workdir: Path, timeout: float = 120.0) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=timeout)


def unittest_passes(workdir: Path, *, label: str = "visible tests pass") -> Check:
    proc = _run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."], workdir)
    tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return Check(label, proc.returncode == 0, " | ".join(tail))


def hidden_tests_pass(workdir: Path, hidden_file: str) -> Check:
    target = workdir / "tests" / hidden_file
    shutil.copy(HIDDEN_ROOT / hidden_file, target)
    try:
        proc = _run([sys.executable, "-m", "unittest", f"tests.{hidden_file[:-3]}"], workdir)
    finally:
        target.unlink(missing_ok=True)
    tail = (proc.stderr or proc.stdout).strip().splitlines()[-3:]
    return Check(f"hidden tests pass ({hidden_file})", proc.returncode == 0, " | ".join(tail))


def check_script_passes(workdir: Path) -> Check:
    proc = _run([sys.executable, "scripts/check.py"], workdir)
    tail = (proc.stdout + proc.stderr).strip().splitlines()[-4:]
    return Check("scripts/check.py exits 0", proc.returncode == 0, " | ".join(tail))


def changed_files(workdir: Path) -> list[str]:
    proc = _run(["git", "status", "--porcelain", "--untracked-files=all"], workdir)
    rows = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        rows.append(path)
    return sorted(rows)


def paths_unchanged(workdir: Path, prefixes: tuple[str, ...]) -> Check:
    proc = _run(["git", "status", "--porcelain", "--untracked-files=all", "--", *prefixes], workdir)
    dirty = [line[3:].strip() for line in proc.stdout.splitlines() if line.strip()]
    return Check(f"unchanged: {', '.join(prefixes)}", not dirty, "modified: " + ", ".join(dirty) if dirty else "byte-identical")


def changes_within(workdir: Path, allowed: set[str]) -> Check:
    changed = changed_files(workdir)
    outside = [path for path in changed if path not in allowed and not path.startswith("tests/") and "__pycache__" not in path]
    return Check("changes stay within the expected files", not outside, "changed: " + (", ".join(changed) or "(nothing)") + (f" | outside: {outside}" if outside else ""))


def file_matches(workdir: Path, relative: str, pattern: str, *, expect: bool, label: str) -> Check:
    path = workdir / relative
    if not path.is_file():
        return Check(label, False, f"{relative} missing")
    found = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE) is not None
    return Check(label, found == expect, f"/{pattern}/ {'found' if found else 'absent'} in {relative}")


def count_in_file(workdir: Path, relative: str, needle: str) -> int:
    path = workdir / relative
    return path.read_text(encoding="utf-8").count(needle) if path.is_file() else -1


def cli_output(workdir: Path, *argv: str) -> subprocess.CompletedProcess:
    return _run([sys.executable, "-m", "ledgerly.cli", *argv], workdir)


def answer_mentions(text: str, needles: list[str], *, label: str) -> Check:
    lowered = text.lower()
    missing = [needle for needle in needles if needle.lower() not in lowered]
    return Check(label, not missing, "missing: " + ", ".join(missing) if missing else "all present")


def line_of(workdir: Path, relative: str, needle: str) -> int:
    for number, line in enumerate((workdir / relative).read_text(encoding="utf-8").splitlines(), start=1):
        if needle in line:
            return number
    return -1


def answer_cites_line(text: str, relative: str, line: int, *, tolerance: int = 3, label: str) -> Check:
    """Accept `path:line`, `path line N`, `path (line N)`, `path#LN` within tolerance."""
    stem = Path(relative).name
    candidates = [int(m) for m in re.findall(rf"{re.escape(stem)}[^\d\n]{{0,24}}?(\d{{1,4}})", text)]
    hit = any(abs(number - line) <= tolerance for number in candidates)
    return Check(label, hit, f"expected {stem}:{line}±{tolerance}; cited {sorted(set(candidates))[:12] or 'nothing'}")


def verification_after_last_edit(analysis: dict, *, label: str = "ran a verification command after the last edit") -> Check:
    ok = bool(analysis.get("verification", {}).get("afterLastMutation"))
    return Check(label, ok, f"verification commands: {analysis.get('verification', {}).get('commandCount', 0)}")


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------


def seed_bugfix_local(workdir: Path) -> None:
    replace_once(workdir, "ledgerly/ledger.py", "if first <= tx.date <= last]", "if first <= tx.date < last]")


def grade_bugfix_local(workdir: Path, ctx: GradeContext) -> list[Check]:
    return [
        unittest_passes(workdir),
        paths_unchanged(workdir, ("tests/",)),
        changes_within(workdir, {"ledgerly/ledger.py"}),
        file_matches(workdir, "ledgerly/ledger.py", r"first <= tx\.date <= last", expect=True, label="range is inclusive again"),
        verification_after_last_edit(ctx.analyses[-1]) if ctx.analyses else Check("verification", False, "no analysis"),
    ]


def grade_feature_multifile(workdir: Path, ctx: GradeContext) -> list[Check]:
    return [
        unittest_passes(workdir),
        hidden_tests_pass(workdir, "test_tags_hidden.py"),
        changes_within(workdir, {"ledgerly/models.py", "ledgerly/storage.py", "ledgerly/ledger.py", "ledgerly/cli.py", "README.md"}),
        verification_after_last_edit(ctx.analyses[-1]) if ctx.analyses else Check("verification", False, "no analysis"),
    ]


def grade_explore_locate(workdir: Path, ctx: GradeContext) -> list[Check]:
    text = ctx.final_text
    return [
        Check("no files changed", not changed_files(workdir), ", ".join(changed_files(workdir)) or "clean"),
        answer_mentions(text, ["importers.py", "dedupe_key", "normalize_description"], label="names the deciding function and normalizer"),
        answer_mentions(text, ["date", "amount", "description"], label="lists the three compared fields"),
        answer_mentions(text, ["cli.py", "skipped"], label="traces the skipped count to the CLI"),
        answer_cites_line(text, "ledgerly/importers.py", line_of(workdir, "ledgerly/importers.py", "def dedupe_key"), label="cites dedupe_key's line"),
        answer_cites_line(text, "ledgerly/models.py", line_of(workdir, "ledgerly/models.py", "def normalize_description"), label="cites normalize_description's line"),
    ]


def seed_debug_failing_test(workdir: Path) -> None:
    replace_once(
        workdir,
        "ledgerly/reports.py",
        "def category_totals(transactions: list[Transaction], totals: dict | None = None) -> dict[str, Decimal]:\n"
        '    """Sum amounts per category. Pass an existing dict to accumulate into it."""\n'
        "    if totals is None:\n"
        "        totals = {}\n",
        "def category_totals(transactions: list[Transaction], totals: dict = {}) -> dict[str, Decimal]:\n"
        '    """Sum amounts per category. Pass an existing dict to accumulate into it."""\n',
    )


def grade_debug_failing_test(workdir: Path, ctx: GradeContext) -> list[Check]:
    return [
        unittest_passes(workdir),
        paths_unchanged(workdir, ("tests/",)),
        changes_within(workdir, {"ledgerly/reports.py"}),
        file_matches(workdir, "ledgerly/reports.py", r"totals: dict = \{\}", expect=False, label="mutable default removed"),
        verification_after_last_edit(ctx.analyses[-1]) if ctx.analyses else Check("verification", False, "no analysis"),
    ]


def grade_refactor_preserve(workdir: Path, ctx: GradeContext) -> list[Check]:
    store_error_handlers = count_in_file(workdir, "ledgerly/cli.py", "except StoreError")
    missing_messages = count_in_file(workdir, "ledgerly/cli.py", "no ledger at")
    return [
        unittest_passes(workdir),
        hidden_tests_pass(workdir, "test_cli_snapshot_hidden.py"),
        paths_unchanged(workdir, ("tests/", "ledgerly/ledger.py", "ledgerly/storage.py", "ledgerly/models.py")),
        changes_within(workdir, {"ledgerly/cli.py"}),
        Check("StoreError handled in one place", 0 < store_error_handlers <= 1, f"'except StoreError' appears {store_error_handlers}x"),
        Check("missing-store message emitted from one place", 0 < missing_messages <= 1, f"'no ledger at' appears {missing_messages}x"),
        verification_after_last_edit(ctx.analyses[-1]) if ctx.analyses else Check("verification", False, "no analysis"),
    ]


def seed_iterate_terminal(workdir: Path) -> None:
    replace_once(workdir, "ledgerly/models.py", "import re\nimport uuid\n", "import os\nimport re\nimport uuid\n")
    replace_once(
        workdir,
        "ledgerly/storage.py",
        '    fd, tmp_name = tempfile.mkstemp(',
        '    print(f"saving {len(transactions)} transactions to {path}")\n    fd, tmp_name = tempfile.mkstemp(',
    )
    replace_once(
        workdir,
        "ledgerly/reports.py",
        'CSV_COLUMNS = ("date", "amount", "description", "category")',
        'CSV_COLUMNS = ("amount", "date", "description", "category")',
    )


def grade_iterate_terminal(workdir: Path, ctx: GradeContext) -> list[Check]:
    analysis = ctx.analyses[-1] if ctx.analyses else {}
    check_runs = analysis.get("verification", {}).get("checkScriptRuns", 0)
    return [
        check_script_passes(workdir),
        paths_unchanged(workdir, ("tests/", "scripts/")),
        changes_within(workdir, {"ledgerly/models.py", "ledgerly/storage.py", "ledgerly/reports.py"}),
        file_matches(workdir, "ledgerly/reports.py", r'CSV_COLUMNS = \("date", "amount", "description", "category"\)', expect=True, label="CSV header order restored (not the test weakened)"),
        Check("ran the check script at least three times", check_runs >= 3, f"scripts/check.py runs observed: {check_runs}"),
        verification_after_last_edit(analysis),
    ]


def seed_recover_from_failure(workdir: Path) -> None:
    replace_once(
        workdir,
        "ledgerly/importers.py",
        'def dedupe_key(tx: Transaction) -> tuple:\n'
        '    """Two rows are the same transaction when date, amount and normalized description match."""\n'
        "    return (tx.date, tx.amount, normalize_description(tx.description))\n\n\n",
        "",
    )
    replace_once(
        workdir,
        "ledgerly/importers.py",
        "    seen = {dedupe_key(tx) for tx in ledger.transactions()}\n"
        "    for tx in parse_rows(text, category=category):\n"
        "        key = dedupe_key(tx)\n",
        "    seen: set[tuple] = set()\n"
        "    for tx in parse_rows(text, category=category):\n"
        "        key = (tx.date, tx.amount, tx.description.strip())\n",
    )
    replace_once(
        workdir,
        "ledgerly/importers.py",
        "from .models import Transaction, normalize_description, parse_amount, parse_date\n",
        "from .models import Transaction, parse_amount, parse_date\n",
    )


def grade_recover_from_failure(workdir: Path, ctx: GradeContext) -> list[Check]:
    analysis = ctx.analyses[-1] if ctx.analyses else {}
    recovery = analysis.get("recovery", {})
    return [
        unittest_passes(workdir),
        paths_unchanged(workdir, ("tests/",)),
        changes_within(workdir, {"ledgerly/importers.py", "ledgerly/models.py"}),
        # Informational: whether the environment actually forced a recovery loop.
        # A model that reads every test before editing can solve this in one pass,
        # which is a benchmark-design signal (make the seed harder), not a failure.
        Check(
            "recovery loop observed (informational)",
            True,
            ("yes: " if recovery.get("failedVerificationThenEdit") else "no first-attempt failure occurred: ")
            + f"failed verifications after an edit: {recovery.get('failedVerificationAfterEditCount', 0)}, "
            + f"edits after such a failure: {recovery.get('editsAfterFailedVerification', 0)}",
        ),
        verification_after_last_edit(analysis),
    ]


def seed_verify_runtime(workdir: Path) -> None:
    replace_once(
        workdir,
        "ledgerly/reports.py",
        '        value = totals.get(category, Decimal("0.00"))\n'
        "        if value == 0 and category not in totals:\n"
        "            continue\n",
        "        value = totals[category]\n",
    )


def grade_verify_runtime(workdir: Path, ctx: GradeContext) -> list[Check]:
    analysis = ctx.analyses[-1] if ctx.analyses else {}
    august = cli_output(workdir, "--store", "sample/ledger.json", "report", "--month", "2026-08")
    july = cli_output(workdir, "--store", "sample/ledger.json", "report", "--month", "2026-07")
    runtime_runs = analysis.get("verification", {}).get("runtimeCommandRuns", 0)
    return [
        Check("report 2026-08 exits 0", august.returncode == 0, (august.stderr or august.stdout).strip().splitlines()[-1:] and (august.stderr or august.stdout).strip().splitlines()[-1] or ""),
        # Either rendering of an absent category (omitted, or shown as $0.00) is a
        # legitimate fix; the prompt did not specify, so the grader must not either.
        Check("report 2026-08 shows the right totals", "$2,340.70" in august.stdout and "food" in august.stdout and "income" in august.stdout, august.stdout.strip().replace("\n", " / ")[:200]),
        Check("report 2026-07 still renders every category", july.returncode == 0 and all(c in july.stdout for c in ("food", "rent", "transport", "utilities", "income")), july.stdout.strip().replace("\n", " / ")[:160]),
        unittest_passes(workdir),
        paths_unchanged(workdir, ("sample/", "tests/test_models.py", "tests/test_ledger.py", "tests/test_importers.py", "tests/test_cli.py")),
        changes_within(workdir, {"ledgerly/reports.py"}),
        Check("actually ran the report command during the turn", runtime_runs >= 1, f"ledgerly.cli invocations observed: {runtime_runs}"),
        verification_after_last_edit(analysis),
    ]


def grade_multi_turn(workdir: Path, ctx: GradeContext) -> list[Check]:
    turn2 = ctx.analyses[-1] if len(ctx.analyses) >= 2 else {}
    package_calls = sum(count_in_file(workdir, rel, ".summary(") for rel in ("ledgerly/ledger.py", "ledgerly/reports.py", "ledgerly/cli.py", "tests/test_ledger.py"))
    return [
        unittest_passes(workdir),
        file_matches(workdir, "ledgerly/ledger.py", r"def monthly_summary\(", expect=True, label="method renamed"),
        file_matches(workdir, "ledgerly/ledger.py", r"def summary\(", expect=False, label="old name gone"),
        Check("no remaining .summary( call sites in package or tests", package_calls == 0, f".summary( occurrences: {package_calls}"),
        file_matches(workdir, "README.md", r"monthly_summary", expect=True, label="README uses the new name"),
        file_matches(workdir, "README.md", r"\.summary\(|`summary`", expect=False, label="README no longer mentions the old name"),
        answer_mentions(ctx.final_text, ["ledger.py", "reports.py", "README.md", "test_ledger.py"], label="final answer lists every file changed across both turns"),
        Check("no stale-digest errors in turn 2", turn2.get("edits", {}).get("staleDigestErrors", 0) == 0, f"stale digest errors: {turn2.get('edits', {}).get('staleDigestErrors', 0)}"),
        Check(
            "turn 2 received the change ledger from turn 1",
            bool(turn2.get("changeLedger", {}).get("injected")),
            f"ledger: {turn2.get('changeLedger')}",
        ),
    ]


TASKS: list[Task] = [
    Task(
        id="bugfix-local",
        title="Simple localized bug fix",
        capability="find a failing test, locate the one-line cause, fix, re-verify",
        failure_modes=["fixing the test instead of the code", "no re-run after the edit", "over-broad exploration for a local fix"],
        seed=seed_bugfix_local,
        turns=[
            "The test suite in this repo has failing tests. Run it, find the root cause, and fix it in the "
            "library code. Do not modify anything under tests/. Re-run the suite and report the result."
        ],
        grade=grade_bugfix_local,
        allowed_changes={"ledgerly/ledger.py"},
        protected=("tests/",),
    ),
    Task(
        id="feature-multifile",
        title="Multi-file feature implementation",
        capability="implement one feature across model, storage, ledger, and CLI without breaking old data",
        failure_modes=["partial implementation declared done", "breaking load of existing files", "losing track of which files were already edited"],
        turns=[
            "Add tag support to transactions:\n"
            "- `Transaction` gets a `tags: tuple[str, ...]` field, default empty. Tags are normalized on "
            "construction: stripped, lowercased, duplicates removed, original order kept.\n"
            "- `to_record()` writes `tags` as a list and `from_record()` accepts records that have no `tags` "
            "key, so ledger files written before this change still load unchanged.\n"
            "- `Ledger.with_tag(tag)` returns the transactions carrying that tag (case-insensitive), in ledger order.\n"
            "- CLI: `add` accepts a repeatable `--tag` option; `list` accepts `--tag` to filter.\n"
            "Keep every existing test passing, add tests for the new behavior, and run the suite."
        ],
        grade=grade_feature_multifile,
        allowed_changes={"ledgerly/models.py", "ledgerly/storage.py", "ledgerly/ledger.py", "ledgerly/cli.py", "README.md"},
    ),
    Task(
        id="explore-locate",
        title="Repository exploration: find where a behavior lives",
        capability="answer a where/how question with precise citations and no edits",
        failure_modes=["broad search dumps", "re-reading files already read", "citing lines it never opened"],
        access=None,
        turns=[
            "When a user runs `import-csv`, some rows are reported as skipped duplicates. Explain exactly how "
            "duplicate detection works in this repo: which function decides that two transactions are the "
            "same, which fields it compares and how each field is normalized before comparison, and where the "
            "CLI's skipped count comes from. Cite file paths with line numbers for each claim. Do not modify "
            "any files."
        ],
        grade=grade_explore_locate,
        allowed_changes=set(),
    ),
    Task(
        id="debug-failing-test",
        title="Debugging a failing test with a non-obvious cause",
        capability="reason about test-order-dependent state instead of patching the symptom",
        failure_modes=["editing the test", "misdiagnosing the cause", "declaring done without running the full suite"],
        seed=seed_debug_failing_test,
        turns=[
            "tests/test_reports.py fails when the whole suite runs but passes when that test file runs alone. "
            "Find the root cause and fix it in the library code, not in the tests. Confirm with the full suite."
        ],
        grade=grade_debug_failing_test,
        allowed_changes={"ledgerly/reports.py"},
        protected=("tests/",),
    ),
    Task(
        id="refactor-preserve",
        title="Refactoring without changing behavior",
        capability="extract duplicated code while preserving every observable behavior, including the asymmetric ones",
        failure_modes=["making add/import-csv require an existing store", "changing error text or exit codes", "skipping verification because the change 'is mechanical'"],
        turns=[
            "ledgerly/cli.py repeats the same store-loading prelude in every command handler (resolve the "
            "path, report a missing ledger, load it, report a StoreError). Extract that into one helper so each "
            "handler calls it once. Observable behavior must not change at all: same stdout, same stderr "
            "messages, same exit codes for every command, including on a missing or corrupt store. Run the tests."
        ],
        grade=grade_refactor_preserve,
        allowed_changes={"ledgerly/cli.py"},
        protected=("tests/",),
    ),
    Task(
        id="iterate-terminal",
        title="Several terminal iterations to reach green",
        capability="drive a gate script to green when each run reveals only the next problem",
        failure_modes=["fixing one gate and stopping", "weakening the checker or tests", "not re-running after each fix"],
        seed=seed_iterate_terminal,
        turns=[
            "`python scripts/check.py` fails in this repo. Make it exit 0 by fixing the real problems it "
            "reports. Do not modify scripts/check.py or anything under tests/."
        ],
        grade=grade_iterate_terminal,
        allowed_changes={"ledgerly/models.py", "ledgerly/storage.py", "ledgerly/reports.py"},
        protected=("tests/", "scripts/"),
    ),
    Task(
        id="recover-from-failure",
        title="First attempt should fail; agent must recover",
        capability="treat a failed verification as new evidence and iterate to a complete fix",
        failure_modes=["declaring victory after the first green-looking edit", "identical retry after a failure", "comparing frozen dataclasses with fresh ids"],
        seed=seed_recover_from_failure,
        turns=[
            "Several tests in tests/test_importers.py and tests/test_cli.py fail. Fix CSV import duplicate "
            "detection so the whole suite passes. Do not edit anything under tests/."
        ],
        grade=grade_recover_from_failure,
        allowed_changes={"ledgerly/importers.py", "ledgerly/models.py"},
        protected=("tests/",),
    ),
    Task(
        id="verify-runtime",
        title="Verification requires running the program",
        capability="fix a crash no test covers and prove it by executing the command",
        failure_modes=["fixing by inspection without running it", "verifying only the reported month", "editing sample data"],
        seed=seed_verify_runtime,
        turns=[
            "`python -m ledgerly.cli --store sample/ledger.json report --month 2026-08` crashes with a "
            "traceback. Fix the bug and confirm the report works for both 2026-08 and 2026-07. Do not modify "
            "anything under sample/."
        ],
        grade=grade_verify_runtime,
        allowed_changes={"ledgerly/reports.py"},
        protected=("sample/",),
    ),
    Task(
        id="multi-turn-continuation",
        title="Two turns: the second depends on remembering the first",
        capability="carry an accurate model of its own edits into the next turn without re-deriving or going stale",
        failure_modes=["stale expected_digest from a replayed earlier read", "re-reading everything edited last turn", "misreporting which files changed"],
        turns=[
            "Rename the `Ledger.summary` method to `monthly_summary` everywhere it is defined or used "
            "(library code, CLI, tests). Run the tests when done.",
            "Now update README.md so its examples and module table use the new name. Run the tests again, and "
            "then tell me exactly which files you changed across both turns.",
        ],
        grade=grade_multi_turn,
        allowed_changes={"ledgerly/ledger.py", "ledgerly/reports.py", "ledgerly/cli.py", "README.md"},
    ),
]

TASKS_BY_ID = {task.id: task for task in TASKS}
