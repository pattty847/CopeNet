# Async Operations Fabric — Vision & Execution Brief

Date: 2026-09-22  
Status: shaped; implementation not started  
Source investigation: [`../unreal-agent-comparison.md`](../unreal-agent-comparison.md)

## Vision

CopeNet agents should be able to launch several safe, independent pieces of work,
continue making progress while slow work runs, accept operator steering immediately,
and survive process interruption without lying about what happened.

The product outcome is not "parallel tools." It is a durable operations fabric for
long-running agent work:

- market evidence, web research, repository inspection, tests, and simulations can
  overlap when their effects are independent;
- the operator can redirect an active run without first killing it;
- completed results wake the agent without model-authored polling;
- reload and restart show the true state of work;
- policy, provenance, freshness, approvals, artifacts, and observability remain stronger
  than in a terminal-only coding harness;
- fewer redundant model turns and repeated input tokens improve cost efficiency without
  lowering answer quality.

Unreal Agent is evidence that this model is useful. It is not the architecture to copy
verbatim. CopeNet should adopt the operation lifecycle while preserving its product and
security model.

## The underlying problem

Today a CopeNet run is synchronous at several levels:

- a provider may return multiple tool calls, but the harness awaits them serially;
- a tool invocation has only a terminal `ToolExecutionResult`;
- one admitted message owns one in-flight run and a second message cannot steer it;
- live tool state is process-local and interrupted rather than recovered after restart;
- approval waits block the current execution path;
- the frontend assumes terminal results closely follow their calls.

This wastes wall time and model turns, but latency is not the deepest issue. Slow tools,
operator input, provider calls, approvals, and recovery are all coupled inside one nested
run. The harness cannot represent "accepted, still running, independently cancelable,
and eventually delivered" as durable state.

The three trading systems make this particularly valuable. Independent price/fundamental
fetches, web evidence, scans, backtests, and repository verification should not force a
single-file line of execution. At the same time, financial evidence has freshness and
provenance requirements that make naive concurrency actively dangerous.

## Product experience

### Normal run

1. The operator sends a goal.
2. The agent issues independent calls in one model turn.
3. Eligible calls visibly enter `queued` and `running`; unsafe combinations remain
   serialized.
4. The agent can continue with available evidence rather than polling.
5. Completions are coalesced briefly, persisted, and delivered in a later model turn.
6. The final answer lands only when the goal is complete or the run has an honest
   terminal reason.

### Steering

The composer remains usable during a run. A steering message is persisted immediately
and shown as "queued for this run." It is consumed once at the next safe model boundary.
It does not silently cancel independent operations or pretend the active provider request
has already seen it.

Steering is a distinct action, not an overloaded second `chat.send`. The initial API
should be `chat.steer` with a caller-generated input ID for deduplication.

### Recovery

After reload or restart, the operator sees each call as queued, running, completed,
failed, canceled, interrupted, or uncertain. CopeNet never labels a side effect
"canceled" merely because its waiter disappeared.

### Approval

An approval-required call is blocked before operation dispatch. Independent safe reads
may continue. Approval is durable, correlated to the exact call, and visually distinct
from ordinary running work.

## Essential scope

The first serious initiative includes:

- explicit execution/concurrency metadata on tool descriptors;
- durable tool-call and operation records;
- a single coordinator that owns session/run state mutation;
- bounded scheduling and resource conflict checks;
- completion coalescing;
- normalized operation lifecycle events;
- correct call-ID correlation live and after reload;
- a provider compatibility matrix;
- restart reconciliation and honest unknown-outcome states;
- run usage aggregated across multiple internal model turns;
- a distinct, durable steering inbox.

## Later opportunities

- remote operation workers and sandbox daemons;
- per-operation cancellation and operator inspection;
- dependency graphs between operations;
- background market scans that attach to live agent work;
- reusable operation types across agents, workflows, and scheduled jobs;
- a Go worker for hardened process supervision if measurements justify it;
- task-aware scheduling across the three trading systems.

## Non-goals

- rewriting CopeNet in Go;
- replacing `ToolExecutionResult`, artifacts, projections, receipts, run records, or the
  transcript model;
- running all model-emitted calls concurrently;
- claiming exactly-once external side effects;
- weakening Barricade, Access, approval, change-ledger, or freshness semantics;
- adopting unrestricted Bash as the primary capability model;
- optimizing benchmark scores before the product behavior is truthful.

## Existing-system fit

Keep these current sources of truth:

- `core/tools/contracts.py`: tool identity, safety, evidence, and side-effect metadata;
- `core/tools/registry.py`: lookup, scope, Access, Barricade, and terminal inline execution;
- `core/harness/tool_loop_responses.py` and `tool_loop_prompted.py`: provider-specific
  conversation representation;
- `ToolExecutionResult`: terminal normalized result;
- artifact materialization, previews, receipts, and tool-step projection;
- append-only transcripts;
- terminal `RunStore` summaries and provider-reported usage;
- run traces as an audit sink, never a recovery store;
- the ordered turn trail and inspector UX.

Add one focused subsystem:

```text
src/copenet/core/operations/
  contracts.py       versioned call and operation values
  store.py           SQLite persistence and atomic admission
  scheduler.py       bounded concurrency and resource conflicts
  coordinator.py     single owner of model/input/operation ordering
  recovery.py        redispatch, reconcile, interrupt, uncertain
  executors/         local operation implementations
```

SQLite is the recommended live-state store. CopeNet already uses it elsewhere, and it
provides atomic call-plus-operation admission, unique idempotency constraints, indexed
recovery, and compare-and-swap updates. `RunStore` should remain the immutable terminal
summary rather than becoming a mutable job database.

## Core data model

```text
ToolCallRecord
  call_id
  session_key
  run_id
  model_turn_id
  sequence
  tool_id
  normalized_arguments
  activity_title
  status
  operation_ids
  policy_snapshot
  submitted_at / updated_at

OperationRecord
  operation_id
  call_id
  type / schema_version
  status / revision / fencing_token
  attempt
  execution_guarantee
  idempotency_key
  recovery_policy
  resource_keys
  serialized_state
  bounded_result or artifact_id
  submitted_at / started_at / updated_at / completed_at
```

Initial operation states:

```text
ready → running → completed | failed
              ↘ cancel_requested → canceled | completed_after_cancel | uncertain
```

`awaiting_approval` belongs to the call/proposal, before an operation can start.

Recovery must be explicit per operation:

- `redispatch`: safe and idempotent;
- `reconcile`: query external state by stable key;
- `interrupt`: cannot be resumed safely;
- `uncertain`: the side effect may have occurred and needs inspection.

## Scheduling and safety

Do not infer parallel safety from `side_effect="read"`. CopeNet's shared
`ToolExecutionContext.ephemeral` currently carries file-read freshness, Barricade taint,
sensitive values, repetition tracking, deferred tools, approvals, chart counts, and live
terminal state.

Add explicit descriptor metadata:

```text
execution_kind: inline | operation
concurrency_class: isolated_read | shared_context | workspace_write | external_effect
recovery_policy: redispatch | reconcile | interrupt
resource_keys: derived file, terminal, chart, account, or external-object locks
```

Initial scheduler rules:

- only explicitly declared isolated reads may overlap;
- writes, external effects, approvals, `tools.load`, `session.standing`, terminal
  lifecycle calls, chart mutations, and shared-context mutations remain serialized;
- a taint-producing read may not overlap a write/external call that could pass
  Barricade before the taint lands;
- model-visible terminal results retain original call order for the first experiment;
- completion order is still recorded truthfully in operation events and traces;
- all concurrency is bounded globally and per session.

Longer term, handlers should return deterministic internal effects for the coordinator to
apply, instead of mutating shared context directly.

## Run and transcript semantics

Recommended definition:

> A run is one operator-visible execution episode. It may contain several model turns,
> operation completions, approvals, and steering inputs.

Each assistant model turn becomes its own append-only transcript segment carrying the
same `run_id`. Do not stretch one mutable assistant message across the episode.

Example:

```text
user initial message
assistant segment: narration + submitted calls
user steering message
assistant segment: steering response + completed results
assistant final segment
```

Provider usage and tool steps aggregate into the one run record; per-model-turn detail
remains queryable in operation/turn records and trace events.

## Provider representation

Unreal sometimes commits a running `function_call_output` and later another final output
for the same call ID. Its own launch post says this pattern is underspecified and rejected
by some providers.

CopeNet must probe both lanes before choosing a representation:

- OpenAI Codex Responses;
- Claude CLI prompted execution.

The safest initial cross-provider representation may be a synthetic coordinator message
listing running calls, followed later by the ordinary terminal result, rather than two
provider-native outputs for one call. This is a hypothesis to test, not a settled design.

## Language decision

Keep the coordinator and operation kernel in Python.

The hard problems are semantics, policy ordering, persistence, provider compatibility,
recovery, transcript truth, and UX—not CPU throughput. A Go rewrite would introduce IPC,
duplicate or remotely invoke security-sensitive Python state, and make it impossible to
know whether experimental gains came from the execution model or the language change.

Python `asyncio`, task groups, subprocess APIs, and SQLite can coordinate far more I/O
concurrency than this product currently needs.

A Go component becomes reasonable only as a later executor behind the same protocol if
measurements demonstrate a need for hardened process supervision, large subprocess
fan-out, remote worker deployment, cgroups/resource enforcement, or a reusable sandbox
daemon. Python remains the product coordinator and policy authority.

## Vertical execution slices

### Slice 0 — Establish evidence

- Add two blocked read-handler timing tests that prove the current loop is serial.
- Add reverse-completion and duplicate-same-tool call-ID tests.
- Probe running/final representations on both provider lanes.
- Record baseline wall time, turns, cache use, tokens, and answer quality.

### Slice 1 — Bounded concurrent terminal batches

- Python-only; no durability or steering yet.
- Allow only declared isolated reads to overlap.
- Emit start events immediately and terminal results in original call order.
- Fix frontend correlation by call ID rather than adjacency or latest tool ID.

This captures simple latency gains while testing the safety metadata. It is not yet the
durable architecture.

### Slice 2 — Durable operation kernel

- Add operation contracts, SQLite store, scheduler, revisions/fencing, cancellation, and
  recovery.
- Start with a dedicated long-running read-only test operation, then one bounded web or
  market read.
- Prove terminal-before-delivery recovery and explicit unknown outcome.

### Slice 3 — Coordinator-driven model turns

- Extract scheduling from the nested provider loops.
- Add immutable request boundaries, completion coalescing, and operation heartbeats.
- Keep Responses and prompted execution as representation adapters.

### Slice 4 — Steering and transcript segments

- Add durable inbox records and `chat.steer`.
- Permit multiple assistant segments per run.
- Aggregate usage and tool steps across model turns.
- Reload active state from durable storage rather than process-local live history.

### Slice 5 — Recovery and broader executors

- Make approvals durable.
- Add safe startup recovery.
- Expand to shell, browser, market jobs, and remote workers only after each has an honest
  cancellation and execution-guarantee contract.

## Verification strategy

Use deterministic clocks, barriers, fake providers, restartable stores, and fault
injection. Benchmarks supplement these tests; they do not replace them.

The prototype is credible only when it proves:

- two eligible reads overlap in wall time;
- calls to the same tool remain correlated by call ID;
- reverse-order completion renders correctly live and after reload;
- taint-producing reads and writes never cross an unsafe scheduling boundary;
- an approval parks without blocking unrelated safe reads;
- call-plus-operation admission is atomic before first dispatch;
- revisions reject stale or terminal-to-nonterminal updates;
- restart resumes, reconciles, interrupts, or marks uncertainty explicitly;
- duplicate dispatch cannot duplicate a retry-safe operation;
- cancel-requested is not mislabeled canceled;
- steering is queued, consumed once, and persisted in correct transcript order;
- both provider lanes receive equivalent semantic input;
- the run record contains complete provider-reported usage across internal turns;
- artifacts, previews, inspector, receipts, change ledger, and `session.standing` remain
  truthful.

## Primary risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Shared-context races | Explicit concurrency classes; coordinator-owned effects |
| Unsafe write/read overlap | Resource keys and Barricade-aware scheduling |
| Duplicate external effects | Execution guarantees, idempotency keys, reconciliation, uncertainty |
| Provider rejects later result | Capability matrix and normalized synthetic fallback |
| Too many completion turns | Short observable grace window and batching |
| Misleading UI ordering | Stable call/operation IDs; separate event and display order |
| Restart loses approvals/steering | Durable inbox and approval records |
| Architecture balloons | One read-only vertical slice before generalization |
| Benchmark chasing distorts product | Require product acceptance criteria and task-level analysis |

## Recommended next move

Authorize a narrow build of Slice 0 and Slice 1. This is reversible, produces real
measurements, fixes already-identified call-correlation assumptions, and tests whether
safe batch concurrency improves CopeNet before the durable kernel is committed.

Do not begin with a Go service, shell execution, writes, in-run steering, or a generalized
workflow engine.
