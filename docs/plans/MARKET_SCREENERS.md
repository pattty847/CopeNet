# TradingView screeners

Implemented 2026-09-10. Market → Screeners (`/market?view=screeners`) discovers
US-listed common shares with five daily setup hypotheses. It uses
[deepentropy/tvscreener](https://github.com/deepentropy/tvscreener), pinned to 0.4.1.
The library's advertised 13,000+ count describes fields across screener types,
not a guaranteed number of tradable assets. This is an unofficial TradingView
interface, with no availability or real-time-data guarantee.

## Workflow

1. Review the universe: default market cap ≥ $10B, price ≥ $10, and approximate
   daily dollar liquidity ≥ $25M. Set an optional market-cap ceiling. Controls
   retain a $1B cap, $5 price and $5M liquidity floor.
2. Review scope and run all five screens. One bounded TradingView request supplies
   the same observation to every setup. Page loads, broker sync and schedules do
   not acquire screener data. Scope changes invalidate the preview; admission
   tokens expire after ten minutes and cannot be reused.
3. Select a setup, inspect the matching rules and values, and sort or search the
   table. Open a name in the ordinary ticker workspace for chart/filing/model
   research. Selection survives a same-tab ticker round trip.
4. Copy selected symbols, export the full evidence JSON, or create a new research
   watchlist. Creation is atomic and refuses existing list names. Lists start with
   role `context`; no existing schedule expands to include them automatically.
   Creation keeps the current watchlist selected. Opening the new list uses the
   existing bounded quote-loading behavior; it does not run a broad research scan.
   Select the named list explicitly in Scans & alerts and preview that scan's
   acquisition scope when ready. Chart research remains an explicit operator action.

| Setup | Daily rules | Initial ordering |
| --- | --- | --- |
| Compression | Bollinger(20) upper−lower ≤ 10% of price; 0–10% below annual high; RSI 40–65 | Narrowest bands |
| Leader pullback | Price > SMA200; SMA50 > SMA200; −2% to +4% from SMA50; 3–15% below annual high; RSI 40–60 | Distance from SMA50, ascending |
| Oversold large caps | Cap ≥ $15B and operator minimum; 15–40% below annual high; RSI 25–38 | Lowest RSI |
| Breakdown watch | Price < SMA50 < SMA200; RSI 30–48; negative one-month return; no more than 15% below SMA200 | Lowest distance from SMA200 |
| Volume expansion | Relative volume ≥ 1.5×; absolute daily move 2–10%; direction follows the move | Highest relative volume |

These are uncalibrated research hypotheses, not expected-return forecasts. The
size/liquidity floor does not test solvency, valuation or business quality. Tight
Bollinger bands do not prove a multi-stage volatility contraction. Trend alignment
does not establish benchmark-relative strength. Volume does not identify the buyer
or prove institutional activity. Oversold names can continue falling; short borrow
and financing costs are outside this feature.

## Contracts and evidence

Business logic lives in `core/market/scans/screeners/`: `models.py` owns strict
configuration and versioned presets, `source.py` owns the vendor boundary,
`evaluate.py` owns pure eligibility, and `service.py` owns admission, observations
and handoff receipts. `rpc_market_screeners.py` validates transport input; five
literal `market.screeners.*` routes are registered in `rpc_routes.py`.
The frontend has a typed API and a dedicated `sections/market/screeners/` directory.

The query filters type=stock, subtype=common, NASDAQ/NYSE/AMEX, market cap and
price at the vendor; the normalized rows also pass those gates locally. Liquidity
is **current price × 30-day average share volume**, not true average dollar turnover.
Instrument metadata replaces ticker-suffix guesses. Class-share dots map to the
existing Yahoo chart symbol convention while retaining the original exchange ID.

A single request allows 5,001 rows: the first 5,000 are inspected and an extra row
marks truncation. Counts describe returned scope and local exclusions, not a fixed
whole-market inventory. There is no moving multi-page window. The universe excludes
OTC, preferreds, warrants, ETFs and depositary receipts. Missing eligibility fields
exclude a row; missing setup fields exclude it only from the affected setup. Null
and non-finite values never become zeros. A failed source is an error, not an empty
screen; the previous successful observation remains visible.

Each immutable local run records the configuration, versioned rules, normalized
observations, computed matches, exclusions, request/receipt times, source and per-row
update mode. The actual vendor timestamp is unknown and explicitly null. Technical
values may include the unfinished daily session and quotes may be delayed. Vendor
price basis is not asserted to match the split-only canonical candle cache; these
observations never enter that cache or completed-candle alerts. Last-used configuration,
summaries and the latest-success pointer are separate from immutable runs.

Storage is under the Market root at `scans/screeners/{runs,summaries,handoffs}`.
No account data enters an observation. JSON export adds the operator's selection;
retained observation features and receipt IDs provide a starting point for later
prospective outcome joins, but there is no ML training, historical screener replay,
backtest, automatic candidate scoring, or claim of predictive edge.

## Chart-agent exposure

The workstation screeners are not ticker panels and are not automatically injected
into chart observations. No new model-facing tools are registered. Opening a ticker
uses the existing chart/filing/forecast workflows and their existing frozen evidence
contracts. Whole-screen context and automatic batch model review remain unavailable;
future work must expose the exact saved observation with its source, coverage and
publication-clock semantics instead of silently refetching candidates for a model.

## Verification

- `uv run --extra dev pytest -q tests/unit/test_market_screeners.py tests/unit/test_market_watchlist.py tests/unit/test_market_scans.py tests/unit/test_rpc_routes.py`
- Frontend `npm run lint`, `npm run build`, and the screener/routing/workstation tests.
- `uv run python scripts/verify_market_screeners.py`: built UI → real RPC handlers →
  temporary stores, with a synthetic source. Covers preview invalidation, manual run,
  create-only watchlist handoff, export, empty/error states, retained last success,
  reload, ticker navigation and 390px geometry. Screenshot uses synthetic names only.
- A live adapter smoke check confirmed the vendor field schema and outgoing filters.
  Live vendor results are not committed fixtures or evidence of predictive accuracy.
