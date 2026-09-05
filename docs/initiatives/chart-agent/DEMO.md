# Chart agent demo

Implemented 2026-09-04. The ticker workspace now has a chart-aware companion backed by
ordinary CopeNet sessions, immutable observations and a durable drawing document.

## Try it

1. Open a ticker in Market and select **Agent** above the chart.
2. Choose a provider/model and Quick, Balanced or Deep. Configure indicators normally;
   pan/zoom, or use **Select chart region** to choose a candle window.
3. Ask: “Inspect this region and draw the levels you can justify. Explain the evidence.”
4. Review any requested annotation approval. Expand a tool group to inspect its actual
   call/output. Select a drawing and open its evidence to inspect exact captured rows.
5. Edit an anchor or label, hide/delete an object, or undo a drawing batch. Reload to
   recover the conversation and document. **New chat** starts a separate session while
   keeping the chart's drawings.

The companion captures current state on every send. An in-flight turn keeps its original
observation even if prices, interval, ticker or research settings change. The context
disclosure lists **captured** sources; it does not imply every stored row entered the model.
Tool result replay records the model-facing text; the per-run observation artifact
retains the corresponding structured initial projection. Full tool artifacts can contain
additional rows when the model response budget required a smaller page.

## Model table format

Initial context and `market.chart.read` now present numeric rows as labeled CSV tables.
The surrounding metadata identifies resource/observation, timeframe and source when
available, price basis, status, returned time range, coverage and continuation offset.
Timestamp values remain unchanged; UTC range labels accompany second-based resources.
Unknown units remain unknown. CSV `null` means a recorded gap; an empty cell means that
field was absent. Prose and nested rows remain JSON rather than being flattened.

This changes model presentation only. Captures, exact-read RPC responses and inspector
artifacts retain structured rows. The harness preserves the separate model body through
call-ID stamping, artifact materialization and transcript replay. Model read limits trim
whole rows and return the next offset; no decimal rounding, resampling or TA summary is
introduced. A single oversized row/metadata returns an actionable narrowing error.

A synthetic `o200k_base` measurement with two-decimal OHLCV prices compared the full
model body, including CSV metadata and JSON tool-envelope escaping:

| Candles | Previous pretty JSON | Compact JSON baseline | CSV presentation |
| --- | ---: | ---: | ---: |
| 63 | 3,856 tokens | 2,416 | 1,774 |
| 2,520 | 148,822 tokens | 93,328 | 63,202 |

These are serialization measurements, not billed turn usage or an accuracy evaluation.
The larger benchmark deliberately bypassed read-size limits for comparison; production
still paginates. Different values, decimal precision and tokenizers change the result.

## What ships

| Area | Behavior |
| --- | --- |
| Data | Exact loaded D/W/M candles, viewport/selection, plotted indicator outputs with null gaps, comparison values, financial overlays and source metadata |
| Panels | Committed Overview, Fundamentals, SEC & Events and Synthesis render models, including active settings/filters and timestamps |
| Quote | The same committed value shown in the asset bar, from the existing single subscription; capture does not fetch or recompute data |
| Drawings | Price level, zone, two-anchor trendline and label; semantic candle-time/price anchors; manual tools and model tools share operations |
| Ownership | Agent edits stay in the bound document and its own session layer; a manual edit transfers an object to operator control |
| Durability | SQLite transactions, revision checks, idempotent operations, compensating undo, immutable observations, content-addressed source resources |
| Delivery | Saved and rendered are separate states; comparison/interval/hidden-view states produce honest paint receipts |
| Sessions | Explicit Market target, stable first-send keys, safe retry/history hydration, stop, model selection, durable workspace linkage; Agents selection stays independent |
| Inspection | Existing tool/artifact inspector plus paginated exact drawing evidence, including after a new conversation or manual takeover |
| Account scope | New account panel resources excluded by default. Existing conversation, drawing labels/rationales and profile knowledge are retained; this switch is not historical erasure |

The model receives exactly five tool capabilities for a chart turn:
`market.chart.context`, `market.chart.read`, `market.chart.document`,
`market.chart.apply`, and `market.chart.undo`. Read-only mode excludes the two mutations.
Chart annotation permission does not grant shell or filesystem writes. Existing Barricade
rules still gate writes after untrusted external prose, and approvals show the exact batch.

The UI contributes browser-captured evidence. Hashes prove the identity of those inputs;
they do not independently verify a vendor's data. Source, split-price basis, availability
alignment and forming-candle caveats remain attached.

## Evidence budgets

| Detail | Initial context target (estimated tokens) | Explicit reads per turn | Maximum rows per read |
| --- | ---: | ---: | ---: |
| Quick | 2,000 | 4 | 100 |
| Balanced | 5,000 | 8 | 500 |
| Deep | 10,000 | 12 | 2,000 |

Queries also have output-character limits and expose pagination/coverage. Oversized single
rows require narrower fields or a metadata path. Exact selected candles remain available
at every detail. Complete source observations are stored independently of those budgets;
historical tool output is replayed as bounded references rather than full dataset dumps.

Capture limits are 8 MiB decoded, 32 resources, and 25,000 rows per resource. Documents
allow 200 objects and 20 operations per batch. The default logical stored-payload capacity
is 512 MiB; SQLite indexes, page allocation and WAL overhead are additional. Capacity
failure preserves referenced evidence and fails the new write. Unbound captures expire
after 24 hours (cleanup runs when the store starts); there is no destructive retained-evidence cleanup UI in this slice. Captures upload complete resources inline, with server-side
content deduplication. Reusing uploaded resource references on later requests is a future
transport optimization. Exact queries currently paginate by offset.

## Implementation map

| Concern | Location |
| --- | --- |
| Shared rendered values | `frontend/src/sections/market/useTickerViewModel.ts`, `viewState/` |
| Companion and controller | `frontend/src/sections/market/chartAgent/` |
| Canvas primitive/gestures | `frontend/src/sections/market/drawings/` |
| Client RPC/session targeting | `frontend/src/lib/wsMarketChart.ts`, `wsChatActions.ts` |
| Domain/storage/query/projection | `core/market/chart_workspace/` |
| Host boundary | `host/rpc_market_chart.py`, `host/ws_frames.py` |
| Existing harness integration | `core/orchestrator/market_context.py`, `approval_execution.py`, `requests.py` |
| Scoped model tools | `core/tools/handlers/market_chart.py` |

Frontend paths above are relative to `src/copenet/host`; core/host paths are relative to
`src/copenet`. Storage sits under the session root at `market/chart-workspace.sqlite3`.

## Verification record

- CSV update: 76 targeted tests cover precision/null/missing-field round trips, quoted
  column names, nested/empty JSON, complete-row pagination, raw artifact retention,
  ordinary chart sessions/replay and delivery through all three harness tool loops.
  The offline browser verifier now consumes actual CSV samples before drawing and
  passes its existing evidence/approval/render/mobile checks.

- Frontend type checking, production build and all 522 frontend tests pass.
- 136 targeted backend tests pass, covering exact/null-preserving capture, deduplication, rollback, concurrent
  revision checks, ownership, conflicting/unrelated undo, capacity, render state, restart
  admission and evidence beyond the ArtifactStore's 500-item lookup window.
- Normal harness tests cover native tool loops, resumed Claude input, historical replay,
  context provenance, wrong-owner/scope rejection, and approved/rejected/aborted/stale
  annotation proposals. Existing session/runtime regressions also pass.
- `uv run python scripts/verify_chart_agent.py` uses synthetic acquisition data with real
  RPC dispatch, temporary stores, the normal harness and a deterministic native provider.
  It verifies four manual drawing types, edits, deletion, reload, interval applicability,
  selected ranges, an actual approval, agent drawing/paint acknowledgement, exact evidence
  inspection and batch undo. Layouts at 1600, 1100 and 390 pixels have no horizontal overflow.
- `uv run python scripts/verify_market_loading.py` passes at 1440, 1100 and 390 pixels:
  loading/empty/error/retry/stale states and no incidental scans.
- One live OpenAI Codex **GPT-5.5** run used the normal Responses tool loop against an
  isolated synthetic candle. It read the exact close **11.125**, created one evidence-linked
  level at that value, then reread the saved revision. This was a real model invocation,
  separate from the deterministic browser fixture. Other providers have deterministic
  adapter coverage; they have not all been exercised live for this feature.
- A local Node serializer measurement used 10,000 daily candles (plus weekly/monthly
  series), six plotted indicators and 100 drawings: 30 measured captures after five
  warmups, 2.82 MB payload, p50 **34.3 ms**, p95 **40.5 ms**, maximum **40.9 ms**.
  This is not a browser long-task or network/SQLite latency measurement.

The README screenshot uses synthetic TEST data and a synthetic provider. No account data,
vendor responses, auth material or live model transcript was added as a fixture.

## Next slices

See [Context, tools and evidence efficiency](CONTEXT_AND_TOOLS.md) for the researched
extension contract, current token-accounting limits and proposed evaluation sequence.

Crypto/order-book ingestion will use the existing backend the operator plans to bring in.
Its adapter needs explicit sequencing/gap recovery, decimal precision, depth coverage and
replay semantics. It is not simulated by the present daily/weekly/monthly candle model.

Also deferred: event-driven live commentary, full Market landing-panel adapters, model
actions that add/configure indicators or financial plots, optional vision, explicit retained
evidence cleanup, and browser long-task/end-to-end capture latency profiling. The initial
feature uses on-send observations and a small document reconciliation poll; it never runs
an LLM on each incoming tick.
