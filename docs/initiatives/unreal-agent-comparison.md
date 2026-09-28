# Unreal Agent vs. CopeNet: Initial Harness Notes

Date: 2026-09-22  
Unreal Agent checkout: `../unreal-agent`  
Inspected revision: `b7c9bf1c5c2fa4127255c07727a7c8413e23944a` (`v0.1.1`)  
Upstream: <https://github.com/unreallabsai/unreal-agent>  
Launch post: <https://unreallabs.ai/blog/unreal-agent/>

## Bottom line

Unreal Agent contains a genuinely interesting execution model, not just a concurrent
`gather()` around a conventional tool loop. It separates a model tool call from the
durable operations that implement it:

1. A synchronous, non-I/O translator validates a call and produces one or more
   serializable operations.
2. The call status and initial operation snapshots are persisted together.
3. An operation manager runs each operation as an actor-like state machine and emits
   durable updates.
4. The context immediately represents unfinished calls with a running placeholder.
5. The model can receive steering, heartbeats, and completed results while other calls
   remain in progress.
6. Each completion can wake another model turn; calls that are still running remain
   visible as running rather than forcing the model to poll them.

This is materially different from CopeNet today. CopeNet passes
`parallel_tool_calls=True` to the Responses API, but both its Responses and prompted
loops execute a returned batch with a serial `for` loop and await each handler before
continuing. CopeNet also locks a session to one in-flight run, so a second user message
does not steer that run.

The strongest idea to investigate is therefore not merely parallel execution. It is a
durable, event-driven operation lifecycle beneath the existing tool contract.

## What shipped publicly

The public repository is an MIT-licensed Go library plus a runner and Harbor adapter.
Its public surface is intentionally narrow:

- providers: OpenAI, OpenAI Codex, OpenRouter, Fireworks, and Ollama
- built-in tools: Bash, ViewImage, and skill use
- append-only, forkable sessions
- in-memory session inbox with caller-supplied input IDs for deduplication
- a single coordinator event loop per session
- a swappable operation manager with local and remote-job paths
- versioned, serializable operations and session formats
- crash recovery and operation resume
- hard stop and stop-when-idle modes
- asynchronous user steering and periodic tool heartbeats
- a minimal prompt that explicitly teaches the model to issue wide batches of
  independent work

The README says this is a selection from a larger internal codebase. The public project
was imported on 2026-09-22, has 132 public commits, about 10.6k non-test Go lines and
28.4k test lines under `harness/`, and currently says it cannot review external pull
requests.

## The asynchronous mechanism

### Coordinator

`harness/coordinator/loop.go` multiplexes four event sources:

- new inbox inputs
- operation updates
- model responses
- heartbeat and short tool-grace timers

Only one model request is active at a time. Operation completions do not cancel an
active model request; they are persisted and delivered on the next model turn. New
external input can cause a turn while operations are still running. A hard stop cancels
the model and all nonterminal operations, while stop-when-idle drains work.

The one-second tool grace period is a useful small detail: completions from a newly
issued batch get a chance to coalesce before another model call. Channel draining also
collects bursts of up to 100 events with a 1 ms idle boundary.

### Tool call versus operation

A translator is deliberately pure and synchronous. It maps one model call to zero or
more operations and returns a `CallStatus` containing validation failure or
`WaitingFor` operation IDs. Result formatting is also owned by the translator.

An operation is a versioned value with an ID, status, serialized state, output bound,
and idempotency data. The local operation manager advances operation state machines in
response to primitive events. Multiple operations can be live concurrently. Remote job
handlers use the same update contract.

This boundary gives Unreal several properties that a task-per-call implementation would
not automatically provide:

- persist-before-dispatch
- idempotent redispatch after recovery
- deterministic cancellation states
- terminal results correlated with the original model call
- local or remote execution without changing the coordinator
- bounded output and explicit operation versions

### Model-facing behavior

The context builder initially returns:

> Tool call is still running. Its result arrives in a later turn: continue with
> independent work, or end your turn to wait for it.

When the operation completes, the running placeholder is removed and a final result for
the same call is appended. The prompt tells the model to issue independent work in the
same turn and never poll.

There is an important compatibility caveat in Unreal's own launch post: two results for
one call (running, then final) are underspecified by the Responses API and were rejected
by some non-OpenAI inference providers. This must be tested independently for every
CopeNet provider lane before adopting the representation.

## Benchmark claim: supported, but not fully reproducible yet

The launch post reports GPT-6 Astra at xhigh reasoning on Terminal-Bench 4.0:

| Agent | Resolution rate | Reported total cost | Difference from Codex |
| --- | ---: | ---: | ---: |
| Unreal Agent | 57.9% | $1,428 | 39.2% lower |
| Codex leaderboard baseline | 57.9% | $2,350 | baseline |
| Pi | 55.0% | $1,827 | 22.9% lower than Codex |

The linked public Harbor job contains 330 trials (66 tasks, five trials), currently
reports 192 passes (58.18%), 608.4M total tokens, 1.84M tokens per trial, and a 96%
cache-hit rate. The launch table's 57.9% does not exactly match the current linked
aggregate.

The cost comparison needs an explicit caveat. Unreal's Harbor adapter deliberately sets
`context.cost_usd = None`, and the linked Harbor page says no per-trial inference cost is
available. The $1,428 total is therefore a vendor-side reconstruction on the launch page,
not a number independently exposed by that public Harbor job. The Codex number is also a
leaderboard baseline rather than a linked same-job rerun. The claimed 40% is arithmetically
consistent, but the exact price reconstruction and comparison protocol are not fully
auditable from the repository. The exact Unreal revisions named by the linked benchmark
jobs are also absent from the public Git history, which begins after those runs. Several
current Harbor aggregates differ from the launch table, so the links are mutable evidence,
not immutable receipts of the published values.

Other launch comparisons show the same direction with smaller savings:

- SWE-Atlas Codebase Q&A: $936 versus Codex $1,303, with 65.8% versus 63.3%
- DeepSWE 1.1: $1,367 versus Codex $1,633, with 72.4% versus 69.0%
- ALE-CLI: $217 versus Codex $292, with 30% versus 29% full pass

These are promising, vendor-run results. They are evidence for a controlled CopeNet
experiment, not yet evidence to replace CopeNet's loop.

## Architectural comparison

| Concern | Unreal Agent | CopeNet today | Implication |
| --- | --- | --- | --- |
| Primary shape | Small agent SDK/runtime | Full operator harness and product | Compare runtime ideas, not total feature count |
| Tool execution | Tool call translates to durable operations | Registry awaits a handler and returns one result | Durable operations are the key missing abstraction |
| Same-response batches | Operations dispatched independently | Returned calls are awaited serially | CopeNet leaves straightforward latency on the table |
| Long-running calls | First-class running state and later completion | Handler/run stays awaited, or a bespoke persistent-terminal tool is polled | Unreal generalizes a pattern CopeNet handles per tool |
| Steering | Inbox accepts input while calls run | `in_flight_run_id` rejects another session run | Requires admission and transcript semantics, not only the tool loop |
| Recovery | Operation snapshots resume and redispatch | Run records are durable, but live tool execution is not resumed | Persist-before-dispatch is attractive for long work |
| Session history | Append-only event log with forks | Append-only transcript plus run, trace, artifact, and state stores | CopeNet has richer records but more cross-store coordination |
| Context | Running placeholder replaced by later final result | Completed result appended before next model request | Provider compatibility is the main protocol question |
| Output control | Per-operation maximum, compact Bash result | Model body, preview, full artifact, replay and within-turn receipts | CopeNet is substantially richer here |
| Tool disclosure | Tiny fixed registry | Deferred disclosure and scoped manifests | CopeNet should retain its model-facing tool catalog design |
| Policy | Prefers sandbox/environment enforcement outside harness | Deterministic Access policy, Barricade, approvals, freshness checks | Do not copy Unreal's security philosophy wholesale |
| UX/observability | JSONL runner and Harbor trajectory | Live ordered turn trail, inspector, activity proof, run explorer | Async states must fit existing UI truth contracts |
| Multi-provider behavior | Normalized adapters around complete responses | Native Responses and prompted Claude CLI lanes | Representation must work in both lanes |
| Compatibility stance | Versioned sessions and operations, best-effort backwards compatibility | No back-compat by default; explicit migrations only | Adopt the abstraction without adopting their compatibility policy |

## What CopeNet should borrow

### 1. Separate call acceptance from execution completion

The current `ToolExecutionResult` is terminal. A future contract should represent:

- accepted/rejected call
- one or more submitted operation IDs
- operation status updates
- final formatted result

Policy and approval must run before an operation is committed for dispatch. A pending
operator approval is a separate state from a running operation.

### 2. Persist before dispatch

For any resumable operation, CopeNet should atomically record the accepted call and its
initial operation values before side effects begin. Updates should be full snapshots or
strictly versioned events. Redispatch must be idempotent.

### 3. One session event loop

Unreal's coordinator is easier to reason about than unrelated background tasks updating
shared state. A CopeNet version would own model calls, operation updates, steering,
approvals, cancellation, and completion coalescing for one session.

### 4. Coalescing and no-poll semantics

The grace window and prompt instruction are cheap, testable ideas. They may reduce
model-turn count even before full crash-resumable operations exist.

### 5. Treat operation managers as replaceable

CopeNet's local process execution, browser work, market jobs, and possible remote
sandboxes should share a lifecycle contract even when their actual executors differ.

## What CopeNet should not copy blindly

- Do not use unrestricted Bash as the architecture. Keep exact tool IDs, Access policy,
  Barricade, approvals, file freshness, and evidence metadata.
- Do not replace CopeNet's artifacts, result projections, receipts, or run records with a
  single session JSONL log.
- Do not launch write/external calls concurrently merely because a model emitted them in
  one response. Ordering, shared mutable context, approvals, and conflicts need explicit
  scheduling rules.
- Do not describe CopeNet calls as parallel until wall-clock tests prove overlap. The
  existing `test_responses_loop_handles_parallel_tool_calls` verifies that both calls are
  accepted and paired, but not that they execute concurrently.
- Do not rely on duplicate running/final `function_call_output` items without a provider
  compatibility matrix.
- Do not infer benchmark cost from token counts without a published pricing and cache
  accounting method.

## Suggested experiment sequence

### Experiment A: measure the current gap

Add a deterministic harness test with two independently blocked read-only handlers. It
should record start/end times and establish that the current loop is serial. This gives a
baseline for both wall time and trace ordering.

### Experiment B: bounded concurrent terminal results within one model step

Prototype concurrent execution only for an allowlist of `side_effect in {none, read}`
tools whose handlers do not mutate shared ephemeral context. Preserve model result order
by original call order, regardless of completion order. Keep writes, external effects,
`tools.load`, approvals, and context-mutating tools serial.

This experiment tests easy latency gains, but it is not the Unreal architecture.

### Experiment C: operation contract spike

Create a design-only operation record with at least:

- operation ID, session key, run ID, turn ID, and call ID
- type and schema version
- ready/running/canceling/completed/failed/canceled status
- tool side-effect and policy metadata
- serialized state and bounded result/artifact reference
- idempotency key
- submitted, started, and updated timestamps

Use one naturally long-running, read-only tool first. Web fetch or a dedicated test tool
is safer than shell or file mutation.

### Experiment D: in-run steering

Decide whether steering extends the active run or creates another internal model turn
inside it. CopeNet's current session lock, transcript message identity, turn trail,
`session.standing`, run usage accounting, and finalization all assume one admitted user
message owns the run. This semantic decision is more important than the asyncio code.

### Experiment E: provider protocol matrix

For OpenAI Codex Responses and Claude CLI prompted execution, test:

- one running call followed by its final result
- two calls completing in reverse order
- a completion arriving while a model response is active
- steering while calls remain active
- cache behavior before and after replacement/finalization
- abort and restart with an unfinished operation

### Experiment F: fair benchmark

Run the same model, effort, task set, timeout, sandbox, tool set, and pricing method across:

1. current CopeNet serial loop
2. bounded concurrent batch execution
3. durable asynchronous operations

Track pass rate, input/cache/output tokens, model turns, tool calls, wall time, failures,
and cost where provider-reported cost exists. Also inspect task-by-task overlap rather
than relying only on aggregate pass rate.

## Questions for the next review with Claude

1. What is the smallest operation abstraction that works with CopeNet's existing
   `ToolDescriptor` and `ToolExecutionResult` rather than creating a second tool system?
2. Should an operation live under a run, a session, or both when it can outlive the model
   turn that launched it?
3. Can an active run safely accept steering without violating append-only transcript
   ordering or provider continuation state?
4. Which CopeNet tools are genuinely independent and read-only, including mutation of
   `ToolExecutionContext.ephemeral`?
5. How should `tools.load`, change-ledger freshness, and Barricade taint propagate across
   overlapping operations?
6. What should happen when one call in a model-emitted batch requires approval while
   independent read calls could proceed?
7. Should completion order or original call order control model-visible result order?
8. How do reverse-order completions render in the live turn trail and after reload?
9. Does a heartbeat consume a full model turn, and under what timeout is that cheaper
   than waiting?
10. Can Responses input legally contain running and final outputs for one call across all
    providers CopeNet supports?
11. How are token usage and terminal reason attributed when one operator-visible run has
    several event-driven internal model turns?
12. Which failure/recovery invariants deserve fault-injection tests before any production
    executor uses the design?

## Verification status

- Repository cloned successfully beside CopeNet.
- Source, tests, runner, Harbor adapter, public launch post, and linked Harbor records
  were inspected.
- Homebrew Go 1.27.1 was installed. The full race suite passes under UTC, as do `go vet`,
  formatting, runner build, 23 Harbor adapter tests, and Harbor Ruff checks. Under the
  local `America/New_York` timezone, one HTTP-date retry test fails because it formats
  local wall time with a literal GMT suffix; this is a test portability defect.
- No Unreal Agent code was modified.
