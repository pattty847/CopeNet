# Lizard hotspot audit and resolution plan

Date: 2026-09-10. Source baseline: `5bf202b`. Status: audit complete; implementation not started.

## Verdict

`send_chat` needs to coordinate the whole turn, but 840 NLOC in one function is not justified. Its responsibilities have different failure semantics, yet share one large exception boundary and mutable local state. There are observable correctness failures, not just a complexity score to improve.

Do not rank these functions by CCN alone. RPC routing is mostly a catalog of independent methods. Fact packets mostly conditionally format independent facts. Admission, terminal persistence, and stream completion carry much greater behavioral risk.

Reproduced with Lizard 1.24.0:

| Function | NLOC | CCN | Assessment |
| --- | ---: | ---: | --- |
| `core/orchestrator/runtime.py:send_chat` | 840 | 155 | Highest structural risk; split lifecycle stages and repair terminal ownership. |
| `host/rpc_dispatch.py:_route_rpc` | 269 | 130 | Mostly routing breadth; replace repetitive branching with an explicit catalog. |
| `core/tools/projection.py:_preview_payload` | 132 | 74 | Dead branches, retired identifiers, and untyped output paths; clean before extraction. |
| `core/market/fact_packets.py:ticker_fact_packet` | 144 | 58 | Mostly justified missing-data decisions; extract coherent formatters, preserve evidence. |
| `providers/openai_codex.py:_parse_responses_sse` | 91 | 57 | Necessary protocol state mixed with permissive recovery; correctness work first. |

Paths below are relative to `src/copenet/` unless stated otherwise. Line numbers describe the baseline, not future locations.

## Findings

### P1 — Run persistence depends on successful event delivery

`core/orchestrator/runtime.py:936–1008` sends the error frame before creating the failed run. If the emitter also fails, execution skips the durable error record, failure trace, dedupe update, and chart admission update. Cleanup still runs through `finally`.

Synthetic orchestrator probe: an emitter that always raises produced **zero durable run records** after provider output began. This is a reproducible callback-failure path; no production disconnect frequency was measured.

The opposite failure occurs at `runtime.py:865–929`: the success record is appended before the final frame is delivered. If only final delivery raises, the generic exception handler appends an error record for the same run. `core/runtime/runs.py:146` is append-only; this is not an overwrite. The probe produced **`['ok', 'error']` for one run**.

Resolution: give execution completion and delivery failure distinct ownership. Persist one terminal execution record before terminal notification; record delivery failures separately. Never retry a model/tool turn merely because notification failed. Preserve a cached terminal result that reconnect/retry can recover. Ensure chart admission converges on the same terminal outcome. Storage failures must remain explicit rather than being swallowed as notification failures.

### P1 — Incomplete Responses streams can release unconfirmed tool calls

`providers/openai_codex.py:468–473` flushes every pending named function call after the loop, including ordinary EOF and abort. A synthetic stream ending after `output_item.added` emitted `responsesFunctionCall` followed by `responsesCompleted: False`.

`core/harness/tool_loop_responses.py:138–163` collects the calls but ignores `responsesCompleted`. On an un-aborted EOF, it can proceed to tool execution; with no calls, it marks the turn completed. The later abort check does prevent tool execution when the abort event is set, so this finding does not claim that cancellation always executes tools.

Resolution: incomplete/failed/truncated responses must not authorize tool execution or success. Track terminal status explicitly, reject incomplete EOF, and discard pending calls on cancellation. Preserve the tested missing-item-done recovery only when a successful terminal response confirms the complete call; otherwise remove it. Add a harness-level side-effect counter test, not only a parser metadata assertion.

### P2 — Answer provenance disagrees across persisted outputs

`runtime.py:576–590` learns the resolved model, and run records use it at `runtime.py:812`. Assistant transcripts (`:753`), answer artifact metadata (`:727`), and final frames (`:897`) still use the requested model.

Synthetic provider announced a different model: the run record used the resolved model while the assistant transcript retained `fake-model`. Existing resolved-model tests cover the run and trace, not those other outputs.

Resolution: use the answering model for finalized assistant output and answer artifacts. Keep requested model as request provenance and preserve the operator-selected session binding. Do not rewrite historical transcripts or silently change the session model.

### P2 — Preview cleanup is incomplete and the current guard misses it

`core/tools/projection.py:137` still recognizes retired `files.search` and `files.list`; `:310–324` also classifies retired identifiers such as `context.prepare`. The second search block (`:183–199`) is unreachable: the earlier block already returns for the identical list condition.

The second shell block (`:202–214`) cannot add successful stdout/stderr handling beyond the first. It only retains an old untyped command-only shape on otherwise unmatched bodies. Artifact branches (`:200–201`, `:215–219`) return `{artifactId, preview}` with no declared `type`; a real `artifact.create` output uses that shape. A direct probe confirmed it.

`tests/unit/test_preview_renderability.py` scans literal type names. An output with no type is invisible to this guard. A passing test therefore does not establish that all actual preview results satisfy the frontend contract.

Resolution: remove retired identifier support and redundant branches in a dedicated cleanup commit. Return a declared renderable preview or the existing bounded raw fallback for artifacts. Replace dual `text`/`snippet` reads with the current producer contract after checking all active producers. Add output-based tests for every projector and artifact/policy/error cases. Keep raw fallback: it is current behavior for arbitrary tool output, not backward compatibility.

### P2 — Reasoning deduplication operates at response scope instead of item scope

`providers/openai_codex.py:372, 409, 450` uses one `saw_reasoning_delta` flag. If item A streams deltas and item B arrives only as a completed reasoning item, B is discarded. Synthetic two-item input emitted only A's text.

Resolution: track streamed reasoning by item identity (and content/summary index where applicable). Suppress duplicates for the same item only. Test interleaved items, done-only items, and delta-plus-done for one item.

### P2 — Cancellation and partial failure need explicit lifecycle coverage

Static inspection: `runtime.py:936` catches `Exception`, which does not include `asyncio.CancelledError`. Task cancellation reaches cleanup without this terminal persistence path. Provider failure after partial text/tool events also skips the successful assistant transcript append. This is a coverage/design gap in this audit; the cancellation and partial-replay cases were not dynamically reproduced.

Resolution: define explicit interrupted-run finalization, preserve produced activity with an honest interrupted state, and re-raise task cancellation after bounded cleanup. Verify replay pairing before persisting incomplete tool calls. Do not turn interrupted content into a successful final answer. Review setup/admission failure ownership as well: chart reservation occurs before session binding validation and before the main `try`.

### Lower priority — Routing and fact formatting need structure, not feature removal

`_route_rpc` already delegates business logic. Its main problem is a mixture of an `elif` catalog and three handler maps, with several legitimate signatures (tasks, broadcast, quote subscription, parameterless calls). No routing defect was confirmed. Preserve connection-scoped quotes, sender responses, broadcast events, background task tracking, error translation, and unknown-method responses.

`ticker_fact_packet` is a pure formatter with about a dozen evidence sections. Most `None` checks are necessary availability decisions, not redundant trust-boundary validation. Do not replace them with zeros or suppress provenance to reduce CCN. The EPS branch at `fact_packets.py:352` labels zero EPS as negative; change this to non-positive or distinct zero/negative wording. A P/E without EPS would also fail formatting, but the audit has not established that a canonical producer can emit that combination; establish the producer invariant before adding defensive coercion.

## Implementation sequence

Each stage is a separate coherent change. Add the missing behavior tests before its fix; preserve correct behavior without freezing confirmed bugs into golden expectations.

1. **Terminal lifecycle correctness.** Add tests for failed delta/error emit, failed final emit, setup failure, task cancellation, partial provider failure, chart admission convergence, and duplicate sends. Extract `run_finalization.py` with one terminal persistence owner. Keep lock release in `send_chat` until ownership tests pass. Repair resolved-model stamping here because finalization owns those records.
2. **Responses correctness.** Add truncated EOF, explicit failure/incomplete response, abort, duplicate call completion, missing done with confirmed completion, interleaved calls, and per-item reasoning tests. Fix the parser and harness contract together. Test zero tool side effects for an incomplete response, including when arguments happen to be valid JSON.
3. **Preview deletion and contract repair.** Delete obsolete IDs, shadowed search logic, and untyped shell/artifact paths. Update direct imports/tests atomically; do not leave aliases. Test actual returned preview shapes, clipping counts, artifact recovery, raw Market results, and policy-only output.
4. **Finish decomposing `send_chat`.** After lifecycle behavior is pinned down, make it a readable sequence: validate/resolve attachments → admit under lock → prepare input → run harness → consume events → finalize → release. Keep public `send_chat` as the single entrypoint.
   - `run_admission.py`: dedupe, active-run checks, session binding and reservation ownership. Keep chart-specific policy in existing `market_context.py`.
   - `run_input.py`: history, attachments, composed instructions, tool policy, context budgeting and harness arguments. Move identity overlay work to a focused module if this exceeds the module threshold.
   - `run_events.py`: one typed accumulator for text, parts, tool receipts, resolved model and sequence; named handlers for current event kinds. Preserve the fact that one metadata event can contain several payloads.
   - `run_finalization.py`: artifacts, append-only transcript, session state, terminal run record, dedupe outcome. Separate optional title/memory/briefing work into `run_notifications.py` when needed to stay within the threshold.
   - Use small typed stage results, not `locals()` checks, a giant context dictionary, or a generic plugin pipeline. Move `_normalize_tool_step` (CCN 36) into the canonical tool receipt boundary; avoid merely relocating the same repeated coercion.
5. **RPC catalog.** Introduce `rpc_routes.py` with literal method-to-named-handler mappings and a small typed dispatch context. Normalize signatures in the current handlers; use explicit specialized handlers for chat/fleet tasks, quotes, and `runtime.context`. Delete the superseded chain and old map ownership in the same commit. Assert duplicate registration fails and test the complete method inventory plus signature exceptions. Update the AGENTS.md instruction that currently prescribes the `elif` chain.
6. **Fact packet formatters.** Extract ticker formatting into a focused `ticker_fact_packet.py`, separating technical sections from fundamentals/news/evidence as needed. Update every importer in the same commit and remove the old implementation; do not re-export it as a compatibility alias. Use explicit ordered calls, not a formatting DSL. Test full/sparse/thin/no-volume inputs, zero and negative EPS, benchmark overlap, base-rate sample threshold, evidence/news limits, section order, units, and basis/provenance text.

## No-backward-compatibility rules for this work

- One canonical implementation, tool ID, event shape, and import path. Delete superseded implementations with their replacements; no `_v2`, aliases, dual readers, or fallback dispatch to old code.
- Update all current callers, frontend types/renderers, tests, and affected docs together if an internal contract changes. Keeping an unchanged public method name is not a compatibility shim.
- Do not delete valid provider boundary handling just because it is a fallback. The currently documented JSON/SSE content-type variation and active `run`/`stream_responses` interfaces need caller/evidence review before consolidation. Prefer one shared parser with explicit current outputs; retain the two active interface contracts where needed.
- Do not rewrite durable transcripts to repair this audit. If a persisted schema must change, specify an explicit one-time migration and removal condition; do not introduce a permanent dual-read path. The proposed extractions do not inherently require a storage migration.

## Verification and acceptance

Audit verification: all five reported metrics reproduced exactly. **86 tests passed** across `test_openai_codex_responses`, `test_openai_codex_provider`, `test_preview_renderability`, `test_market_interpretation`, `test_orchestrator`, `test_resolved_model`, `test_ws_rpc`, `test_run_records`, and `test_responses_tool_loop`. Temporary in-memory/synthetic probes confirmed the delivery, provenance, EOF, artifact-preview, and reasoning findings above. No live provider calls or operator data were needed. Passing existing tests does not cover the newly exposed cases.

Implementation gates:

- One terminal outcome per admitted run; failed notification cannot erase or change execution outcome. Preserve lock ownership, idempotency, provider/profile/persona/workspace immutability, and explicit model/Access changes.
- No tool execution from incomplete Responses output; correct call pairing, terminal classification, cancellation, and reasoning item deduplication.
- Every non-null preview declares a supported type. Update the renderability test to inspect the new projector modules and actual results so extraction cannot silently remove coverage.
- Run the targeted suites above plus lifecycle tracing, multi-turn Responses replay, chart session, prompt ownership, permissions/approval, and relevant financial tests. Run the full deterministic suite after integration; compile Python and run frontend lint/build when shared event/preview contracts change. Verify affected session/inspector flows in the browser, and restart the actual host after backend implementation per AGENTS.md.
- Re-run pinned Lizard on all changed modules, including extracted files. Aim for `send_chat` under roughly 150 NLOC / CCN 15–20, dispatch/projector entrypoints under CCN 10, and focused helpers generally under CCN 15–20. These are review targets, not a reason to invent abstractions. Explain residual protocol/availability branching rather than spreading it among trivial helpers. Keep Python modules around the 400-line soft threshold.

This commit is documentation only. It does not repair the findings, alter runtime behavior, or require a server restart.
