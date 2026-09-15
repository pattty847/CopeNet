# Coding-agent benchmark

A small suite that runs CopeNet's real orchestrator and tool loop against a
realistic little repository and then reads the trace to ask *how* the harness
behaved, not only whether the model got the answer.

It complements `scripts/agentic_eval.py`, which checks raw capability on
one-file toy tasks. Two families:

- **Fixture family** (`tasks.py`): one multi-module fixture (`fixture/ledgerly`,
  a stdlib-only expense ledger with a CLI, tests and a gate script) with a
  different defect or gap seeded per task, so exploration, verification,
  recovery and edit-tracking all cost something real on a repo the model can
  hold in its head.
- **Large-repo family** (`repo_tasks.py`): the CopeNet checkout itself, in a
  detached `git worktree` of HEAD under a temp directory. This is where search
  discipline, citation accuracy, per-step context growth and cross-turn replay
  at 60–100K tokens actually show up. The real tree is never the workspace.

`catalog.py` joins both into `TASKS` / `TASKS_BY_ID`.

## Fixture tasks

| id | exercises | access |
|---|---|---|
| `bugfix-local` | failing test → one-line cause → fix → re-verify | full-access |
| `feature-multifile` | one feature across model / storage / ledger / CLI, old files must still load | full-access |
| `explore-locate` | where/how question with line citations, no edits | read-only |
| `debug-failing-test` | test-order-dependent failure (mutable default) | full-access |
| `refactor-preserve` | extract duplicated prelude in `cli.py` without changing any behavior | full-access |
| `iterate-terminal` | gate script reveals one problem per run; three iterations minimum | full-access |
| `recover-from-failure` | dedupe fix where the first attempt leaves tests red | full-access |
| `verify-runtime` | crash no test covers; only running the command proves the fix | full-access |
| `multi-turn-continuation` | second turn depends on remembering the first turn's edits | full-access |
| `deferred-tool-load` | a market question in a coding session: the model must `tools.load` a deferred tool before using it | read-only |

## Large-repo tasks

| id | exercises | access |
|---|---|---|
| `repo-where-is-it` | the Debug-capture toggle from React component → RPC → host handler → orchestrator → `observability.json` → `run_admission`, cited per hop | read-only |
| `repo-trace-event` | a `provider_usage_reported` row from `token_usage_event` through the tool loop, `consume_metadata`, and `summarize_token_usage` | read-only |
| `repo-broad-question` | "map the session lock" — a question where `rg lock` returns thousands of matches; graded on the load-bearing names and on search discipline | read-only |
| `repo-fix-gated` | seeded one-line defect in `core/sessions/change_ledger.py` (folded state keeps the first digest); gated by the project's own pytest | full-access |
| `repo-two-turn` | two seeded defects in `core/harness/replay_receipts.py`; turn 2 edits the same file turn 1 edited, so ledger, receipts and cross-turn freshness are all exercised | full-access |

Repo tasks' prompts state the environment honestly: `python` on PATH is this
venv's interpreter and `PYTHONPATH` points at the worktree's `src` (set by the
runner for the task's duration), so `python -m pytest <paths>` tests the
worktree's code and not the editable install of the real checkout. The graders
run pytest the same way. The read-only tasks add two behavior checks: at most
one search returning more than 200 matches, and at most one redundant read.

Every task's grader is independent of anything the model claimed: it runs the
tests, hidden acceptance tests, the CLI, or `git status`, and it reads the trace
analysis for behavior checks (did a verification command run after the last
edit, did a failed verification lead to another edit, and so on).

## Running

```bash
uv run --extra dev python -m benchmarks.coding.run --list
uv run --extra dev python -m benchmarks.coding.run --dry-run           # no model: proves every seeded task starts red
uv run --extra dev python -m benchmarks.coding.run --provider openai-codex --model gpt-5.5
uv run --extra dev python -m benchmarks.coding.run --only repo-where-is-it repo-fix-gated
uv run --extra dev python -m benchmarks.coding.run --repeat 3 --only repo-broad-question
```

`--repeat N` runs every selected task N times, each in a fresh session and a
fresh workspace, round-robin so a slow hour lands on every task's run k rather
than on one task. The report then leads with a per-task table of pass rate and
median (min–max) for tool calls, model calls, peak input, billed input, redundant
reads, search dumps and seconds, with every run listed underneath. Single runs
of the same task swing ±20% on billed tokens and 2→4→2 on search dumps, so a
before/after decision needs at least three runs per side.

`--extra dev` matters for the repo tasks: their graders (and the model) run this
interpreter's pytest. For seeded repo tasks `--dry-run` also proves the gate is
green on an unseeded worktree, so a red result is the seed's doing and not a
pre-existing failure on HEAD. Repo tasks benchmark HEAD, not the working tree.

Runs go through an in-process `Orchestrator()` against the operator's real
`~/.copenet` store, so every run appears in the Observability workspace under a
`bench-<task>-<timestamp>` session. Debug capture is switched on for the
duration of the suite (and restored afterwards) so traces carry full tool
arguments and result bodies. Live runs spend provider quota and execute real
tools inside a temp workspace.

Output lands under `tmp/coding_bench/<timestamp>-<provider>-<model>/`:

- `REPORT.md` / `summary.json` — suite score and per-task table
- `<task>/turnN.trace.jsonl` — the run trace (copied)
- `<task>/turnN.analysis.json` — the trace analysis
- `<task>/turnN.final.md` — the model's final message
- `<task>/workspace.diff` — what the model changed
- `<task>/result.json` — checks, turns, token usage

## Reading a trace

The analyzer works on any run, benchmark or not:

```bash
uv run python -m benchmarks.coding.trace_analysis <run-id>
```

It reports model calls and tool calls, provider-reported and estimated tokens,
which tool results the tokens went to, redundant reads (a range already read
with no intervening edit), reads right after the agent's own edit, exact
repeated calls, stale-digest errors, search dumps, failed calls and blind
retries, verification commands and whether one ran after the last edit, and
whether a failed verification was followed by another edit.

The behavior rules are not the analyzer's own: they live in
`src/copenet/core/harness/coding_metrics.py`, and run finalization applies the
same rules to every real run's tool steps and stamps the compact result on the
run record as `codingMetrics` (shown in the Observability inspector's "How it
worked" section). The analyzer adds what only a trace can give — per-step token
growth, result-body token attribution, timings — on top of that shared core.

## Adding a task

Add a `Task` to `FIXTURE_TASKS` in `tasks.py` or `REPO_TASKS` in
`repo_tasks.py`: a `seed(workdir)` that mutates the pristine source (use
`replace_once` so a drifted source fails loudly), one or more turn prompts, and
a `grade(workdir, ctx)` returning `Check`s. Fixture hidden acceptance tests live
under `hidden/` and are copied into `tests/` only at grading time; repo tasks
gate on the project's own tests through `pytest_passes`. Run `--dry-run`
afterwards: the seeded state must grade red, and a seeded repo task's gate must
be green without the seed.
