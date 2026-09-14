# Coding-harness audit — 2026-09-13

Scope: CopeNet's agent harness as a coding environment. Questions answered here:

1. How the Chat agent and the Chart Agent relate, and whether harness improvements
   propagate to the Chart Agent.
2. What the coding/tool loop actually does, step by step.
3. Where it is likely to fail, and what the traces prove it does fail at.
4. What a benchmark suite for this looks like (`benchmarks/coding/`), and what a
   first run shows.
5. Which changes are justified by that evidence, with the tradeoff for each.

Evidence comes from reading the code at `2713fa6`, from the two large real coding
traces already on disk (`fe35c50b`, `c3302ab1`: gpt-5.5, full-access, the mobile
composer task, 37 and 45 tool calls), and from the first benchmark run. Where a
claim is from a trace, the run id is named.

---

## 1. Architecture: one harness, two front doors

### The pipeline every turn goes through

```
chat.send (WS RPC / REST / CLI `copenet chat send` / Chart Agent panel)
  └ orchestrator.runtime.send_chat
      ├ run_admission.admit_run        session bind, workspace root, trace writer, chart admission
      ├ run_input.prepare_run_input     tool selection (Access policy), system prompt composition,
      │                                 transcript → Responses input[] (responses_items), token budget
      ├ run_harness.start_harness       ChatHarness.run_turn(...)
      │     ├ planning.plan_turn        capability profile → tool_execution_mode
      │     ├ decision.resolve_harness_decision_record   trace-only
      │     └ ONE of three loops:
      │          tool_loop_responses    openai-codex   (native Responses API, streaming)
      │          tool_loop_native       lm-studio      (Chat Completions tool_calls, non-streaming)
      │          tool_loop_prompted     claude-cli / ollama (delimited <copenet:tool> JSON in text)
      ├ run_events.consume_event        parts, tool steps, usage, live frames
      └ run_finalization                transcript append, RunRecord, artifacts
```

Tool execution is shared by every loop: `ToolRegistry.execute` (policy, Barricade,
repetition tracking) → handler under `core/tools/handlers/` → `ToolExecutionResult`
→ `to_model_payload()` (the one model-facing envelope) → `_materialize_tool_result_artifact`
(persist >4,000 chars as an artifact, clip the model copy at 80,000 chars).

### Chart Agent is the same harness with a scoped tool set — improvements propagate

The Chart Agent panel (`sections/market/chartAgent/useChartConversation.ts`) calls the
ordinary `chat.send` RPC with a `marketContext` attached. From there the only
differences are injected at well-defined seams, all of them in the orchestrator, none
in the loops:

| Seam | Where | What the chart lane changes |
|---|---|---|
| Admission | `market_context.resolve_market_context`, `admit_chart_turn` | binds an immutable observation, idempotent admission record |
| Tool selection | `run_tools.select_run_tools` → `chart_workspace.authorization.chart_tool_ids` | replaces the coding manifest with the five `market.chart.*` tools plus `web.search`/`web.fetch`; adds `chart-write` category when access is `annotate` |
| System prompt | `market_context.chart_system_overlay` | appends the chart-collaboration overlay |
| User message | `market_context.current_chart_message` | appends the chart packet (one matrix, budgeted) |
| Tool context | `prepare_chart_tool_context` | carries chart store + external-prose taint into Barricade |
| Replay | `messages._with_chart_references` | stubs old chart tool bodies on the next turn |
| Execution guard | `ToolRegistry.execute` | enforces `chart_tool_ids` independently of the manifest |

The loop code (`tool_loop_*.py`), the result envelope, the artifact materialization,
the token budget, the trace events, the run record, and the transcript parts are
identical. `test_chart_session.py` drives the chart lane through the same
`Orchestrator.send_chat`. So:

- **Anything improved in the loops, the tool envelope, budgeting, tracing, replay, or
  the run record reaches the Chart Agent for free.**
- What does *not* propagate is anything keyed on the coding tool ids
  (`files.*`, `shell.exec`) or on the coding domain prompt. That is the correct
  boundary: the chart lane deliberately has no repo tools.
- The one place where the two lanes carry parallel logic is result shaping for the
  model: `files.*`/`shell.exec` return `output` dicts that the loops JSON-dump, while the
  chart tools set `model_body` (a pre-formatted table) because a JSON dump of a
  candle matrix was unreadable. That is a per-tool presentation choice, not a fork.

Verdict for question 1: clean specialization, not a fork. Improve the core and the
Chart Agent inherits it.

### The three loops are *not* one loop

> Update, later the same day: the LM Studio and Ollama lanes and the Chat
> Completions loop (`tool_loop_native.py`) were removed (`refactor(providers)` and
> `refactor(harness)` commits on `claude/remove-local-providers`). Two loops remain,
> Responses (openai-codex) and prompted (claude-cli), and the integration suite drives
> tool turns through `tests/integration/responses_fake.py`. The paragraph below
> describes the state this audit measured.


The three `run_with_*` functions share helpers (`tool_loop_common.py`) but each owns
its own message array, its own budget check, its own step loop, and its own event
emission. A behavior change (compaction, a state block, verification nudges) has to be
implemented three times or it silently applies to one provider only. The Responses
loop is where all the recent work landed (budget re-check per step, encrypted
reasoning replay, usage forwarding); the native loop raises on over-budget instead of
trimming; the prompted loop re-sends every prior tool exchange inside the user prompt
for non-resumable providers (quadratic growth by construction).

---

## 2. The coding loop, concretely (Responses lane, openai-codex)

Per turn:

1. `select_run_tools` — every registered manifest tool whose category the Access
   policy allows: **18 tools** in full-access, including `market.*`, `memory.*`,
   `persona.author`, `user.remember`, `web.*`. 24,129 chars of JSON schema per
   request (trace `prompt_context_assembled`).
2. `compose_prompt` — base contract + coding domain + Access overlay + persona
   splice (4,661 chars of persona in the real traces) ≈ 17–18K chars. Then
   `compose_responses_tool_instructions` appends a directive that lists every tool id
   again.
3. `build_chat_messages` — the durable transcript replayed as Responses items:
   every prior user message, assistant message, `function_call` and
   `function_call_output` (full `replayOutput` body, not the summary), plus the
   provider's opaque `reasoning` items.
4. `trim_messages_to_request_budget` — drop whole oldest user-turn groups until under
   `min(168K, 60% × window) − reserve(≤25K)`. Never abbreviates anything inside a
   turn.
5. Loop: stream a response; collect `function_call` items; execute each tool
   sequentially; append `function_call` + `function_call_output` to the in-memory
   array; re-POST the whole array. Repeat until a response has no function calls or
   `MAX_TOOL_STEPS = 100`.
6. Finalize: parts (text, thinking, tool_call, tool_result with `replayOutput`,
   `responses_item`) go to the transcript; `RunRecord` gets tool steps and summed
   provider usage.

What the model sees of its own actions: exactly the raw `function_call_output`
strings, forever, verbatim, in order. There is no separate state representation.
The harness *has* a per-run `TurnState` (visited paths, evidence ledger, failed
actions) and a per-run `file_read_state` (path → last digest), but both are
trace/UI-only; the model never sees either.

Fixed cost per model call measured in the benchmark trace (`bench-bugfix-local`):
7,786 input tokens before the first tool result (instructions + 18 tool schemas +
a 40-token user message).

---

## 3. Bottlenecks and failure modes the traces already show

Each item below names the mechanism and the evidence.

**F1. Tool results are append-only and unbounded within a turn.** Context grows
monotonically; nothing is ever summarized, deduplicated or superseded.
`fe35c50b`: 9.4K → 106K input tokens over 29 model calls; total billed input across
the turn ≈ 1.9M tokens for one feature. `bench-bugfix-local`: a one-line fix cost
200,236 billed input tokens across 14 calls (peak 19K).

**F2. The handlers honor absurd limits.** `files.rg` accepted `limit: 20000` and
returned 1,153 matches (`fe35c50b` step 2, +23K tokens in one call) and 8,974 matches
(`c3302ab1` step 2, clipped only by the 80,000-char model backstop). Two searches
consumed ~50K tokens of a 96K budget before a single file was read. The default
`search_result_limit` is 80; the model overrides it because the description invites
paging with `limit`.

**F3. Prompt caching is unreliable, so every step re-bills the whole prefix.**
`bench-bugfix-local` usage per call: cached tokens were 0 on calls 1, 6, 8, 10 and
3,584 on 4, 9, 12 while the prefix was ~7.7K stable tokens and the array only grew.
Averaged, 45% of billed input was cached; the rest was re-sent. `prompt_cache_key`
is set; the misses look provider-side, but the harness does nothing to help
(instructions embed the temp workspace path; the tool list is re-serialized each
call in dict order).

**F4. `expected_digest` is a copy-by-hand protocol, and the model fabricates it.**
`c3302ab1` steps 30 and 33: `files.edit` failed with "stale read detected" for
`index.css` and `index.html`. Every read of those files in that run returned digests
`b46f0c92…` and `1c854e57…`; no earlier turn had read them. The model sent
`f6fc5869…` and `30f4f738…`, which appear nowhere in any tool output — invented
hex. Each cost two extra round trips (re-read, re-edit). The harness already knows
the truth (`file_read_state`) and could enforce freshness itself.

**F5. Redundant reads are not prevented, only identical *consecutive* calls are.**
`_track_tool_repetition` compares a call to the immediately preceding one, so it
never fires in practice. `fe35c50b` re-read `AgentComposer.tsx` 1–40 after reading
1–240, and `index.css` 130–165 after 1–190 (analyzer: 2 redundant reads);
`c3302ab1` read `index.css` in six overlapping slices.

**F6. Plan bookkeeping costs a full model round trip each time.** `plan.write`
returns nothing the model needs, yet each call is a step: 5 of 14 model calls in
`bench-bugfix-local` were plan updates for a one-line fix (the instructions say to
skip it for simple tasks; the tool directive pushes the other way). Tokens are minor;
latency and call count are not.

**F7. Tool selection ignores purpose.** A coding turn carries `market.backtest`,
`market.compare`, `market.dashboard`, `market.evidence`, `market.financials`,
`market.ticker`, `memory.*`, `persona.author`, `user.remember`: 11 of 18 tools and
most of the 24K schema chars are irrelevant to the repo task. The Context Conveyor
plan (2026-07-25) already specified purpose bundles; they were never built.

**F8. Cross-turn replay carries every old tool body verbatim.** `replayOutput` stores
the full model-facing body per tool result and `parts_to_response_items` replays all
of it. A session's second coding turn starts with the whole first turn's file reads
and command output in context; the only relief is dropping *entire* oldest turns when
the budget trips. The chart lane solved this for itself (`_with_chart_references`
stubs old chart bodies to a receipt); the coding lane has no equivalent.

**F9. Shell state does not persist and the model is told so.** Each `shell.exec` is a
fresh `/bin/bash -c` in `workdir`; the coding prompt says to prefer absolute paths.
Models comply by prefixing every command with `cd /abs/path && …` (every command in
both real traces). Works, but wastes tokens and the trace's `target` hint is useless
for those calls.

**F10. Verification is model discipline, not harness structure.** Nothing in the loop
knows that an edit happened without a subsequent test run. Both real traces did
verify; whether weaker models or longer tasks do is exactly what the benchmark
measures (`verification.afterLastMutation`).

**F11. `TurnState` is a dead ledger.** `visited_paths`, `evidence_items`,
`failed_actions`, `open_questions` (never written), `pending_input` (queued and
drained without a reader) are computed every step, serialized into every
`turn_transition` trace row and every live frame, and consumed by nothing that
decides anything. It is the skeleton of the state representation the model should
see, currently paid for and unused.

**F12. Non-monotonic input estimates in older traces.** `c3302ab1` step estimates
fell from 34K to 20K with `omittedItemCount: 0`; the runs predate the tokenizer-count
commit (`6bb66c1`, 2026-09-13), so the numbers are a chars/4 artifact. Benchmark traces
from today are monotonic and match provider usage within ~10%.

---

## 4. Benchmark suite

`benchmarks/coding/` (README there). One fixture repository, `ledgerly`: six
modules, 35 tests, a three-gate `scripts/check.py`, sample data. Nine tasks, each a
seeded defect or gap on that repo, graded independently of the model's claims. The
analyzer (`trace_analysis.py`) turns any run trace into the questions from the brief:
what it inspected, what it called, what came back, redundant reads, edit tracking,
repeats, premature completion (grader vs. claim), verification, where tokens went.

`--dry-run` proves every seeded task grades red before a model touches it.

## 5. First run: openai-codex / gpt-5.5

Baseline run at `2713fa6` (before any change from this audit). All nine tasks passed
on regrade; the one live "failure" (`verify-runtime`) was my grader insisting that
absent categories be omitted from the report when the model chose to print them as
`$0.00`, which the prompt never specified. Grader relaxed; noted here because a
benchmark that over-specifies the fix measures the grader, not the agent.

| task | pass | tool calls | model calls | billed input | peak input | cached | wall |
|---|---|---|---|---|---|---|---|
| bugfix-local | ✓ | 17 | 14 | 200,236 | 19,193 | 45% | 52s |
| debug-failing-test | ✓ | 11 | 11 | 122,509 | 13,669 | 62% | 41s |
| explore-locate (read-only) | ✓ | 8 | 5 | 66,257 | 16,799 | 24% | 70s |
| feature-multifile | ✓ | 37 | 28 | 783,960 | 45,694 | 67% | 166s |
| iterate-terminal | ✓ | 15 | 16 | 185,866 | 15,857 | 72% | 49s |
| multi-turn-continuation | ✓ | 15 + 3 | 9 + 3 | 181,179 | 18,679 | 59% | 50s |
| recover-from-failure | ✓ | 18 | 13 | 271,308 | 26,260 | 69% | 59s |
| refactor-preserve | ✓ | 15 | 16 | 377,232 | 31,350 | 61% | 76s |
| verify-runtime | ✓ | 14 | 11 | 153,812 | 18,063 | 65% | 54s |

Billed input = sum of provider-reported `input_tokens` over the turn's model calls.
Peak = the largest single call. The ratio between them (10–17×) is the cost of
re-sending the whole array every step; the cached column is how much of that the
provider absorbed.

What the traces say, task by task:

- **Correctness and autonomy are not the problem on this fixture.** gpt-5.5 solved
  every task with zero questions back, zero blind retries, zero stale-digest errors,
  zero redundant reads, and verified after its last edit in 9 of 9 runs. The two
  real CopeNet-repo traces are where the harness weaknesses show (search dumps,
  overlapping re-reads, invented digests); the fixture is too small to provoke them.
  The suite needs a "large repo" task family (read-only exploration against the
  CopeNet checkout itself) to reproduce those at scale.
- **The recovery task did not force a recovery.** gpt-5.5 read every failing test
  before editing and fixed all four failures in one pass. That check is now
  informational; a seed whose second failure only surfaces at runtime is needed to
  make it bite.
- **Orientation is a ritual.** 7 of 9 runs opened with `pwd && find/ls …` (one model
  call, 0.6–2K tokens, including `.git/hooks/*.sample` listings) before any real work.
  6 of 9 opened with `plan.write`.
- **`plan.write` is 17% of all tool calls** (26 of 149) and each is normally its own
  model call: 5 of 14 calls on a one-line fix.
- **Envelope overhead measured directly** (debug tier, `feature-multifile`): of the
  tokens the model received back from tools, 100% of `plan.write`, 61% of `files.edit`,
  44% of `shell.exec`, 36% of `files.read` and 32% of `files.rg` were envelope —
  `callId`, `channel`, `target`, `workspaceRoot` (a 90-char temp path), `scope`,
  `accessAction`, `policyDecision`, `policySummary`, `indent=2` — not payload.
- **Cross-turn replay is verbatim.** Turn 2 of `multi-turn-continuation` started at
  18.8K tokens: 32K chars of turn-1 `function_call_output`, 9.5K chars of encrypted
  reasoning, 5.4K of `function_call` arguments. The model handled it well (three
  calls, re-checked with `git diff --name-only` instead of trusting memory), but a
  ten-turn coding session grows the same way until whole turns fall off.
- **Exploration answers were exact.** `explore-locate` cited `importers.py:74` and
  `models.py:54` correctly with no file re-read; the read-only lane is in good shape.
- **The final `content` mashes narration together.** Interstitial sentences streamed
  before tool steps are joined with nothing ("…prove it.Crash reproduced: …") in the
  flattened content used by the CLI, artifacts and titles. Fixed today in
  `run_events.consume_text`.

### After the changes shipped today

S1–S4 below were applied and the four cheapest tasks re-run once each (single
runs; the model's exploration path varies run to run, so read the direction, not
the last digit). Tool-result tokens are what the model received back from tools
over the whole turn; peak input is the largest single model call; billed input is
the sum over all calls.

| task | tool calls | model calls | tool-result tokens | peak input | billed input |
|---|---|---|---|---|---|
| bugfix-local | 17 → 16 | 14 → 14 | 8,239 → 6,681 (−19%) | 19,193 → 15,697 (−18%) | 200,236 → 177,607 (−11%) |
| explore-locate | 8 → 7 | 5 → 4 | 7,697 → 8,103 (+5%) | 16,799 → 15,736 (−6%) | 66,257 → 46,838 (−29%) |
| feature-multifile | 37 → 34 | 28 → 25 | 28,863 → 23,182 (−20%) | 45,694 → 34,672 (−24%) | 783,960 → 607,048 (−23%) |
| multi-turn-continuation | 18 → 17 | 12 → 12 | 9,120 → 8,842 (−3%) | 18,679 → 17,619 (−6%) | 181,179 → 165,382 (−9%) |

All four still pass every check. The envelope change is the whole story on the
edit-heavy tasks (feature-multifile: −20% result tokens with more edits than
before); explore-locate read one more file this time, so its result tokens rose
while its billed input fell with one fewer call. Nothing in the after-run hit the
new `files.rg` cap or the freshness check, as expected on a 700-line fixture —
those two guard against the failures in the real traces, and the large-repo task
family is what will exercise them.

One benchmark defect found while grading: the fixture's `.gitignore` ignored
`ledger.json` by basename, so `sample/ledger.json` was untracked in the seeded
commit and the "sample/ unchanged" check was vacuous. Fixed (`/ledger.json`); the
kept baseline workspace was diffed against the fixture by hand and the sample was
untouched.

## 6. Proposals, each with its tradeoff

Shipped today (each small, each with a test, each measured by re-running the suite):

**S1. Slim the model-facing envelope** (`ToolExecutionResult.to_model_payload`).
Drop `callId`/`channel`; drop the access-policy bookkeeping on allowed calls (blocked
and roaming calls keep it — there it is the reason); no `indent=2`. `plan.write` now
returns its one-line summary to the model instead of echoing the plan (`model_body`);
the checklist UI still reads `output`. *Tradeoff:* the model no longer sees
`workspaceRoot`/`scope` on ordinary calls. It never acted on them; the blocked-call
path is unchanged. Prompted-lane local models get compact JSON instead of indented —
still valid JSON, fewer tokens.

**S2. Cap `files.rg` at 200 matches per call** regardless of `limit`, with a "narrow
the pattern" hint when the total is over 400. *Tradeoff:* an exhaustive
enumeration of a >200-hit symbol needs paging; the two real traces show the
unbounded version is only ever used by accident.

**S3. Harness-enforced edit freshness; `expected_digest` removed from the tool
schemas.** `files.edit`/`files.write` now compare the on-disk digest against the
digest this run last observed (`file_read_state`) and refuse with an actionable
message when they differ. *Tradeoff:* the record is per run, so a file read in turn
1 and edited in turn 2 is not checked — the same gap as before, minus the invented
digests. Persisting last-known digests into session state closes it (P3 below).

**S4. Separate narration segments across tool steps** in the flattened content.

Proposed, in the order I would do them. Each names the evidence and the cost.

**P1. Purpose-scoped tool bundles for the coding lane.** Offer `files.*`,
`shell.exec`, `plan.write`, `web.*` by default; `market.*`, `memory.*`,
`persona.author`, `user.remember` only when requested (`requested_tool_ids`) or via
deferred disclosure. Evidence: 11 of 18 tools and most of the 24K schema chars are
dead weight on every coding call (F7); the Context Conveyor plan already specified
this. *Tradeoff:* a market question asked inside a coding session needs the tool
added explicitly, and this is a product call about what Agents chat does by default
— which is why it is not shipped in this pass.

**P2. Within-turn compaction of old tool results, in the loop, not the transcript.**
After each step, bodies older than the newest N results are replaced in the
*outbound* array by receipts: `files.read` → path, line range, digest, "re-read if
needed"; `shell.exec` → command, exit code, first and last few lines; `files.rg` →
top matches only. Never compact edits/writes (they are the record of change), never
the newest N, never a failing result until a later success on the same target,
never anything in the durable transcript. Evidence: F1 — `feature-multifile` carried
11K tokens of file bodies through 28 calls; `fe35c50b` grew to 106K. *Tradeoffs:*
exact recall of an old body costs one `files.read` (vs. thousands of tokens on every
step); each compaction changes the cache prefix, so batch it every few steps rather
than every step; the analyzer's redundant-read counter is the regression alarm.

**P3. Cross-turn replay as receipts, the way the chart lane already does it.** *(Shipped 2026-09-14 with the change ledger: `core/harness/replay_receipts.py`, newest turn verbatim, edits and failures always verbatim, receipts only when smaller.)*
`_with_chart_references` stubs old chart bodies; generalize it so prior turns' tool
bodies replay as receipts except the most recent turn's. Persist last-known file
digests in session state so S3 also covers turn N+1. Evidence: F8, the turn-2
starting size above. *Tradeoff:* "what did that command print two turns ago" needs
the artifact, which brings up the next item.

**P4. Give the model a way to open the artifacts the hints point at.** *(Shipped 2026-09-14: `artifact.read`, session-scoped, char-paged; hints and receipts name it.)* Every clipped
result says "the full output is saved as artifact X"; no tool reads an artifact by
id. Either add `artifact.read` (read-only, session-scoped) or stop naming artifact
ids to the model and say "re-read with offset". *Tradeoff:* one more tool schema
(small) versus a hint the model cannot act on.

**P5. Orientation preamble on the first turn of a session.** cwd, git branch and a
short status, top-level tree (ignoring `.git`, caches), detected toolchain files,
clearly marked as observation. Evidence: 7 of 9 runs spend their first model call
discovering exactly this, and the `find` output they get includes `.git/hooks`.
*Tradeoff:* ~300 tokens on every first turn; must be cheap to compute and must not
pretend to be instructions.

**P6. Make plan updates free.** Either instruct the model to batch a `plan.write` with
its next real call (parallel tool calls are already on), or condition the
directive on task size. Evidence: F6 (17% of calls, mostly their own round trip).
*Tradeoff:* less granular live checklist updates.

**P7. One step engine for the three loops.** Extract the shared step (budget check →
execute → materialize → record → emit) so the lanes differ only in transport.
Evidence: the per-step budget re-check exists only in the Responses loop; the native
loop raises on overflow; the prompted loop replays every prior exchange inside the
prompt for non-resumable providers. P2, P3 and P5 otherwise have to be written three
times. *Tradeoff:* a refactor in the most regression-prone code; do it with the
existing scripted-provider matrix as the safety net, before P2.

**P8. Redundant-read guard keyed on digest.** When a read's range is fully covered by
an earlier read of the same file, the digest is unchanged, and no edit intervened,
return a receipt instead of the body. Evidence: F5, both real traces. *Tradeoff:*
a model that re-reads to refresh line numbers after an edit is unaffected (the edit
resets coverage); one that re-reads out of habit gets a cheap reminder instead of
the file. Ship after P2, since P2 makes old bodies disappear from context and
increases legitimate re-reads.

**P9. Either feed `TurnState` to the model or delete it.** It already tracks
visited paths, failed actions and evidence per step and is consumed by nothing
that decides. The P2 receipts are the natural place for its content. *Tradeoff:*
none for deletion; for use, the bookkeeping must stay a few hundred tokens or it
becomes the problem it solves.

What I would *not* do: aggressive summarization by a model call (a second model
summarizing tool output loses the exact lines a debugger needs and doubles cost on
short tasks), or shrinking file reads below what the coding prompt asks for
("read enough to be right"). Every measured overrun above came from envelope,
replay and search dumps, not from reading files that needed reading.

Chart Agent inheritance: S1–S4 apply to it unchanged (its tools already use
`model_body`, so S1 changes only their envelope). P2/P3 would replace the chart
lane's private replay stub with the general mechanism, which removes the one
parallel path that exists today.
