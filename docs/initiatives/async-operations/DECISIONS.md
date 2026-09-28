# Async Operations Fabric — Decisions

Date: 2026-09-22

These are FORGE recommendations from the shaping pass. They become implementation
constraints when the initiative is authorized for build.

## D1 — Keep CopeNet's control plane in Python

Status: recommended

Python can express the coordinator, scheduling, persistence, and provider semantics. A
Go rewrite adds migration and IPC risk without addressing the hard problem. Go remains a
possible later worker implementation behind a language-neutral operation protocol.

## D2 — Add an operation layer; do not replace the harness

Status: recommended

Preserve providers, tools, Access, Barricade, artifacts, projections, receipts, traces,
run records, transcripts, and frontend concepts. Insert durable call/operation admission
between policy validation and execution.

## D3 — Keep `ToolExecutionResult` terminal

Status: recommended

Pending/running states belong to call and operation records. Overloading the existing
terminal result would contaminate projections, receipts, artifacts, and model payloads.

## D4 — Make concurrency opt-in and explicit

Status: recommended

Do not infer safety from read/write labels. Add execution kind, concurrency class,
recovery policy, and resource keys. Default every existing tool to serial until audited.

## D5 — Use SQLite for mutable live operation state

Status: recommended

Atomic admission, revisions, idempotency uniqueness, recovery queries, and durable inbox
state fit SQLite better than several coordinated JSON files. Continue emitting immutable
terminal summaries to `RunStore`.

## D6 — Define one run as an execution episode

Status: recommended

A run may contain multiple model turns and steering inputs. Persist each assistant turn
as an append-only segment sharing the run ID. Aggregate usage and tool steps at the run.

## D7 — Make steering an explicit durable action

Status: recommended

Add `chat.steer` rather than silently changing the meaning of a second `chat.send`.
Queue by default; do not cancel an active provider request unless the operator explicitly
chooses interrupt-and-steer in a later design.

## D8 — Start with isolated reads only

Status: recommended

The first concurrency slice excludes writes, external effects, approvals, taint-sensitive
work, deferred tool loading, session standing, chart mutations, and terminal lifecycle.

## D9 — Use honest execution guarantees

Status: recommended

Exactly-once side effects are not promised. Each operation declares redispatch,
reconcile, interrupt, or uncertain recovery semantics. Cancellation is a requested state
until the executor confirms termination.

## D10 — Treat Unreal's benchmark economics as provisional evidence

Status: recommended

The linked Harbor jobs substantiate substantial token use and competitive rewards, but
not the launch dollar totals. Evaluated revisions are absent from the current public Git
history, and current Harbor aggregates do not exactly match the launch table. CopeNet
should run a controlled, same-model experiment before making cost claims.
