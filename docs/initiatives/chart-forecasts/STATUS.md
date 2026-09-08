# Manual chart forecasts

Implemented 2026-09-05 from the founder-approved [roadmap](ROADMAP.md).

## Product flow

Open the chart agent's settings and choose **Forecast this chart**, or use the action
on its Forecasts tab. Choose a concrete model, entry expiry, optional independent
directional comparison, and a reviewed price-tracking scope. Single-run is the default;
paired comparison explicitly adds one model run. A suitable existing focused price scan
is reused by default. Otherwise the request previews its weekday 17:00 New York scope,
including the existing VOO acquisition dependency, before registration.

The model submits an entry, protective stop, target fractions, thesis, evidence and optional
zones, or explicitly declines a setup. Valid output is frozen and plotted. If the harness
requires exact-call approval after external research, the companion displays that approval.
Stopping aborts all unfinished lanes. Reconnects and restarts never regenerate an uncertain
request automatically. Failed attempts and partial pairs remain visible.

The latest setup is visible by default; the eye controls expose earlier overlays. Select
a level or Ledger row to inspect the original setup, exact captured/evaluation evidence,
render receipts, lane attribution, paired answer and amendments. Amendments preserve the
original score. Forecast objects do not enter the editable drawing document.

Ledger has **Calls / Chart forecasts / Comparison**. Provider/model/date filters select the
chart cohort; existing ticker calls retain their historical cohort and scoring semantics.
Direction at four/eight weeks is separate from simulated entry/exit performance. Paired
counts include distinct ticker/date coverage and exclusions. Repeated requests can remain
correlated; these reports do not establish predictive superiority.

## Ownership and invariants

- `core/market/forecasts/`: strict contracts, composed SQLite store, evidence retention,
  attribution, pure evaluator, cached tracking and cohort reports.
- `core/market/chart_prices.py`: one cache revision supplies all rendered timeframes
  and explicit split/completion provenance. Admission/publication validate that exact
  captured revision against local cache; they never acquire substitute prices.
- `core/orchestrator/market_forecasts.py`: manual admission and isolated ordinary harness
  runs. Each lane receives the same frozen resources and detail budget, with account,
  prior-chat, persona and peer-answer isolation. Prompt/evidence hashes, run-model attribution,
  reads and available usage are retained; unavailable billed usage remains unknown.
- `host/rpc_market_forecasts.py`: typed operator boundary. Model submission authority comes
  from the admitted session/run binding, never caller-selected IDs or prose intent.
- `sections/market/forecasts/`: compact request flow, immutable primitive, shared inspector
  and Ledger comparison. `panel:forecasts` declares committed rows and loaded coverage to
  the chart agent. Saved and rendered are separate receipts.

Tracking evaluates completed daily candles through explicit focused price scans and cached
reads. It never calls a model. Exchange-session completion, entry expiry, partial targets,
opening gaps, intrabar ambiguity and hard deadlines are deterministic. A stopped trade can
still be directionally correct at eight weeks. Later splits normalize prices to the original
publication basis; changed consumed history preserves prior evidence and requires review.

## Verification and practical limits

Final verification: 180 targeted backend tests and all 528 frontend tests passed; frontend
TypeScript and production build passed. The offline browser acceptance passed at 320/390px
and desktop, proving a −1R stopped setup alongside an ambiguous, unscored setup while both
retain correct eight-week direction.

Synthetic backend tests cover the evaluator, strict storage, frozen retention, real harness
admission, paired isolation, approval, cancellation, restart and exact source inspection.
`scripts/verify_chart_forecasts.py` exercises the browser through real RPC and scripted
provider lanes, including mobile layouts, immutable chart levels, price catch-up and the
Ledger. Its screenshots contain only synthetic market data and no operator account state.

This release uses completed daily US-equity/ETF candles, even when analysis is weekly or
monthly. Exchange support follows the existing Market symbol/calendar boundary. It does
not reconstruct intraday ordering or simulate liquidity. Scores are gross price results;
fees, spreads, slippage models, borrow and dividend cash flows are excluded. Tracking needs
the host/scheduler and fresh cached data; pause, unavailable scope and stale/gapped data
are visible. Crypto/order books, actual broker orders and notifications remain separate work.

Follow-up UI verification (2026-09-05): the original setup inspector now includes a
proportional price ladder, exact entry/stop/target prices and direction-aware percentage
and R labels. Unit coverage includes shorts and nearly adjacent target labels. All 530
frontend tests, TypeScript and production build pass. Offline browser checks cover the
setup map at 320/390px and the chart's reverse drag, two-tap selection, cancellation,
touch selection without panning, and restored pinch zoom. The former text-only level
layout and its CSS were replaced; original forecast records and scoring are unchanged.

Setup/outcome chart refinement (2026-09-05): replaces the price ladder with a daily-close
line over quiet risk/reward bands. The lead-in is the last 60 completed frozen daily
candles; forward points reuse evaluation `consumedBars`, already normalized to publication
prices and bounded by completed-session/gap rules. The plot keeps the full eight-week
horizon blank until observations arrive, shows retained-evidence health, and labels that
intraday touches can differ from daily closes. Exact levels/returns and the model thesis
expand separately. `market.forecast.get` supplies this bounded projection only when
`includeChart` is requested; opening it performs no additional acquisition or model call.

Verification: 81 focused backend tests and 531 frontend tests passed, plus TypeScript,
production build and offline browser checks at 320/390px and desktop. The browser verifies
both an empty future path and the real evaluated path after synthetic eight-week catch-up.
New screenshots contain synthetic data only. The running host's chart response and health
endpoint were checked after restart.
