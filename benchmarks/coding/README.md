# Coding-agent benchmark

A small suite that runs CopeNet's real orchestrator and tool loop against a
realistic little repository and then reads the trace to ask *how* the harness
behaved, not only whether the model got the answer.

It complements `scripts/agentic_eval.py`, which checks raw capability on
one-file toy tasks. This suite uses one multi-module fixture (`fixture/ledgerly`,
a stdlib-only expense ledger with a CLI, tests and a gate script) and seeds a
different defect or gap per task, so exploration, verification, recovery and
edit-tracking all cost something real.

## Tasks

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

Every task's grader is independent of anything the model claimed: it runs the
tests, hidden acceptance tests, the CLI, or `git status`, and it reads the trace
analysis for behavior checks (did a verification command run after the last
edit, did a failed verification lead to another edit, and so on).

## Running

```bash
uv run python -m benchmarks.coding.run --list
uv run python -m benchmarks.coding.run --dry-run           # no model: proves every seeded task starts red
uv run python -m benchmarks.coding.run --provider openai-codex --model gpt-5.5
uv run python -m benchmarks.coding.run --only explore-locate --provider lm-studio --model <id>
```

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

## Adding a task

Add a `Task` to `tasks.py`: a `seed(workdir)` that mutates the pristine fixture
(use `replace_once` so a drifted fixture fails loudly), one or more turn
prompts, and a `grade(workdir, ctx)` returning `Check`s. Hidden acceptance tests
live under `hidden/` and are copied into `tests/` only at grading time. Run
`--dry-run` afterwards: the seeded state must grade red.
