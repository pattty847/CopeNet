# Async Operations Fabric — Status

Last updated: 2026-09-22

## Current phase

FORGE shaping complete. No CopeNet runtime implementation has started.

## Completed investigation

- Cloned Unreal Agent beside CopeNet at `../unreal-agent`.
- Inspected revision `b7c9bf1c5c2fa4127255c07727a7c8413e23944a` (`v0.1.1`).
- Audited coordinator, inbox, context builder, tool translation, operation manager,
  primitives, session store, local-file recovery, runner, provider adapters, Harbor
  adapter, trajectory conversion, and fault tests.
- Audited CopeNet harness loops, tool contracts/policy, approvals, run admission and
  finalization, session/run/live-history persistence, tracing, transcript assumptions,
  and frontend correlation.
- Independently reviewed launch claims and linked Harbor jobs.
- Installed Homebrew Go 1.27.1.

## Validation results

- `go vet ./...`: passed.
- Go formatting check: passed.
- runner build: passed; `-h` executed.
- `TZ=UTC go test -race ./...`: passed across all packages.
- Harbor adapter unit tests: 23 passed.
- Harbor Ruff lint and format checks: passed.
- Native `America/New_York` Go test run: one failure in
  `TestExchangeRetryHints/HTTP_date`. The test formats local wall time with a literal GMT
  suffix; it passes under UTC. This is a portable-test defect, not an async coordinator
  failure.

All caches, environments, and build outputs used for validation were placed under
`/tmp`; the Unreal checkout was not modified.

## Key corrected findings

- The async architecture is real and materially different from CopeNet's serial handler
  loop.
- Unreal atomically persists the initial call-to-operation linkage before first manager
  dispatch.
- Its local actor can start an internal primitive before the corresponding next actor
  checkpoint reaches durable storage. It is not exactly-once execution.
- The runtime does not enforce its operation idempotency field.
- Concurrency is unbounded and has no resource-conflict scheduler.
- Shell recovery can only report an unknown/interrupted outcome, not reattach reliably.
- Later results may produce a second provider output for the same call ID; portability is
  unresolved.
- CopeNet's Barricade and shared ephemeral context make naive read/write concurrency
  unsafe.
- CopeNet's frontend currently has adjacency and tool-ID fallbacks that are ambiguous
  under reverse-order or duplicate same-tool completion.

## Benchmark status

The launch economics are promising but not independently reproducible from the public
artifacts:

- the Harbor adapter deliberately emits no `cost_usd`;
- launch dollar totals are external reconstructions;
- exact Unreal revisions named by the linked benchmark jobs are not present in the
  public Git history;
- the repository's public root history begins after the benchmark runs;
- current Harbor aggregates differ from several launch-table values, so the links should
  not be treated as immutable receipts of the published table.

## Proposed next milestone

Slice 0 + Slice 1 from `VISION.md`:

1. establish deterministic serial timing and frontend correlation baselines;
2. add explicit concurrency metadata with serial defaults;
3. run bounded, Python-native overlap for audited isolated reads only;
4. preserve original model result order and record actual completion order;
5. compare wall time, model turns, cache/input/output tokens, and correctness.

This milestone needs explicit build authorization because the current FORGE invocation
used the default shaping mode.
