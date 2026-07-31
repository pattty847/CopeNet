# Test Suite Phase 2A

## Scope

Phase 2A implemented the focused contracts approved after the initial audit. It did not
reorganize the test tree, introduce a general test framework, or begin the approval,
application-isolation, or `core.multiagent` architecture work reserved for Phase 2B.

Baseline after cleanup pass 1: 703 Python tests and 90 frontend tests. Phase 2A finishes
with 725 Python tests and 91 frontend tests: 816 total, a net increase of 23 focused
contract cases.

## Market point-in-time and price-basis contracts

- `tests/unit/test_market_financials.py` now drives the public financial-series service with
  an older filing, a newer accounting period not yet available at the simulated time, and a
  later restatement. The as-of result contains only information whose `availableAt <= T`,
  retains accession/source provenance, and does not mutate the source input.
- Valuation observations are filtered using their observation timestamp and EPS availability,
  including observations whose EPS is not yet known.
- `src/copenet/host/frontend/tests/financialOverlay.test.ts` proves chart observation time uses
  `availableAt`, never `periodEnd`.
- `tests/unit/test_market_data_contracts.py` statically checks every direct `fetch_ohlcv` caller
  supplies the literal `auto_adjust=True`. Two callers that previously relied on the default
  now state the split-adjusted contract explicitly.
- Market bar-cache payloads record `priceBasis: split_adjusted`; basis-less or incompatible
  cache entries are rejected so one caller cannot poison another consumer through the shared
  cache key.
- The old slice-independence test was deleted. It only proved that slicing a Python list did
  not include later rows and did not exercise filing availability or a production boundary.

The real portfolio backtester currently consumes price data, not financial-series records.
This phase therefore tests the no-lookahead rule at the canonical financial service and chart
alignment boundaries rather than fabricating a backtester dependency that does not exist.

## Shared tool-loop behavioral contracts

`tests/integration/test_tool_loop_contract.py` provides one local parameterized contract for
prompted, native Chat Completions, and OpenAI Responses loops. Each implementation must prove:

- one tool request is correlated with one execution result and a completed final response;
- an actionable failed tool result is replayed into the provider's real follow-up input;
- aborting after the first call in a multi-call response prevents the second side effect; and
- `MAX_TOOL_STEPS + 1` attempted calls execute exactly `MAX_TOOL_STEPS` times and terminate with
  the cap explanation/status.

The helper is deliberately local and exposes each provider shape explicitly. Existing tests at
higher orchestration boundaries and Responses-specific wire/reasoning boundaries remain.

This contract exposed a production defect: prompted and native loops checked cancellation only
between provider rounds, so a batch could continue executing tools after abort. Both loops now
check before each side effect.

## Persistence concurrency and recovery contracts

Focused tests now cover:

- two `SessionStore` instances concurrently creating sessions without lost updates;
- two transcript and run-store instances concurrently appending without record loss while
  preserving each writer's order;
- interrupted atomic index replacement preserving the last good file and allowing retry;
- truncated final transcript/run JSONL records preserving every valid prefix record;
- corrupt session-state JSON being quarantined and raised rather than overwritten;
- minimal old session, state, and run records receiving backward-compatible defaults; and
- startup recovery clearing a stale marker without appending an interrupted duplicate when the
  same run already has a durable terminal record.

Production file stores now share path-scoped locks inside the process, JSONL append operations
flush and `fsync`, session state uses the common atomic/quarantine helpers, and startup recovery
checks for an existing run record. These changes intentionally provide no cross-process lock.

The supported deployment invariant is documented in `docs/STARTUP.md` and
`docs/SESSION-CONTINUITY.md`: one CopeNet writer process per persistence workspace. Concurrent
threads, tasks, and store instances in that process are supported; multiple writer processes
require a transactional store.

## Defects found

1. Financial data was not defensively filtered by filing availability at the public service
   boundary, and valuation filtering could discard not-yet-known EPS observations incorrectly.
2. Shared Market bar-cache entries did not identify their split-adjusted basis.
3. Prompted/native batched tool calls could continue side effects after cancellation.
4. File-store locks were instance-local, allowing same-process instances to race on one path.
5. Startup recovery could append a false interrupted record after a terminal record had already
   become durable but before the session marker was cleared.

## Deferred to Phase 2B

- Specify strict app/resource ownership fields, then run two-app negative attachment/session
  tests before changing the authorization model.
- Design and implement the same-process approval reconnect state machine, including exact
  decision authority, stale/duplicate rejection, reject-versus-abort behavior, and resume once.
- Freeze and audit `core.multiagent` against Fleet, producing a keep/migrate/delete map before
  removing any code or tests.
- Multi-process file-store writers and server-restart approval recovery remain out of scope.

## Commits

- `f170c15 test(market): enforce point-in-time data contracts`
- `ae1de3b test(harness): share tool loop behavioral contracts`
- `72d13d6 test(persistence): enforce same-process recovery contracts`

## Validation

Focused validation completed during each batch:

```text
uv run --extra dev pytest -q tests/unit/test_market_*.py
150 passed in 18.71s

uv run --extra dev pytest -q <focused harness contract and existing harness suites>
53 passed

uv run --extra dev pytest -q tests/unit/test_json_store.py tests/unit/test_session_store.py tests/unit/test_transcript_store.py tests/unit/test_run_store.py tests/unit/test_state_store.py tests/integration/test_run_records.py
49 passed in 0.10s
```

Complete validation:

```text
/usr/bin/time -p uv run --extra dev pytest -q
725 passed in 27.71s
real 28.63

/usr/bin/time -p npm test
91 passed, 0 failed
duration_ms 1070.738625
real 1.34

npm run lint
tsc --noEmit: passed

npm run build
vite build: passed in 1.84s

python3 -m py_compile $(rg --files src/copenet -g '*.py')
passed
```

The Vite build retained its pre-existing dynamic/static-import and large-chunk warnings;
there were no build, lint, type, or test failures.
