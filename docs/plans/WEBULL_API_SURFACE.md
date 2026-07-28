# Webull API Surface — Live Probe Audit (2026-07-28)

What the `webull-openapi-python-sdk` 2.0.12 credentials in `.env` actually grant us, verified by
read-only live calls against the production account (no order/trade calls were made). Re-run the
probe before trusting these results after an SDK or entitlement change.

## Headline

CopeNet uses **3 of ~70** available SDK reads (`account_v2.get_account_list` /
`get_account_balance` / `get_account_position`). The `webull.data` lane — a whole `DataClient` —
is never constructed.

The assumption recorded in `webull/sync.py` ("Webull market data is a separate paid subscription")
is **only true for realtime equity/option quotes**. Fundamentals, analyst data, capital flow,
screeners, watchlists, and crypto all return 200 on our current app credentials.

## Verified: available now (HTTP 200, real data)

### Trade lane — `TradeClient`

| Call | Returns | Notes |
|---|---|---|
| `account.get_account_profile(account_id)` | account_type (`CASH`), account_status | never used; relevant to portfolio context (no margin, settlement rules) |
| `account.get_app_subscriptions()` | subscription/account ids | entitlement introspection |
| `account_v2.get_account_list/balance/position` | — | **the only calls we use today** |
| `order_v2.get_order_history(account_id, page_size, start_date, end_date)` | **full fill records** | `symbol, side, status, order_type, entrust_type, total_quantity, filled_quantity, filled_price, place_time_at, filled_time_at, limit_price` — verified 37 orders / 25 FILLED over 2026-01-01→07-28. Default window is 7 days; pass explicit dates for history. |
| `order_v2.get_order_open` / `order_v3.*` (read methods) | open orders, order detail | v3 shape is the same combo/legs envelope |
| `trade_calendar.get_trade_calendar(market, start, end)` | trading days | **max 30-day range per call** (417 otherwise) |

### Data lane — `DataClient` (never built in CopeNet today)

| Call | Returns |
|---|---|
| `instrument.get_instrument` | instrument ids / listing metadata |
| `instrument.get_company_profile` | description, employees, address, establish date, exchange |
| `instrument.get_analyst_rating` | strong_buy / buy / hold / sell / under_perform counts + effective date (equities only — ETFs return an empty body) |
| `instrument.get_analyst_target_price` | mean / median / low / high target |
| `fundamentals.get_capital_flow` | **daily large / medium / small money in+out** — an institutional-flow proxy with no yfinance equivalent |
| `fundamentals.get_earnings_calendar` | per-quarter `eps_actual/eps_est/rev_actual/rev_est` + expected publish date |
| `fundamentals.get_forecast_eps` | forward EPS estimates incl. unreported quarters |
| `fundamentals.get_financials_alert` | next earnings date + est vs last-year EPS/revenue |
| `fundamentals.get_financials_indicators` | quarterly ratio series (net_margin, diluted EPS, per-share book values, …) |
| `fundamentals.get_financials_income / _cashflow / _balance_sheet` | quarterly statements |
| `fundamentals.get_industry_comparison` | peer ranking within industry on a chosen metric |
| `fundamentals.get_sec_filings` | filing title + SEC URL + publish date |
| `fundamentals.get_dividend_calendar` | declare/ex/record/pay dates + amount |
| `screener.get_market_sectors` / `_detail` | **sector breadth**: advanced / declined / flat counts, volume, change_ratio, market value |
| `screener.get_gainers_losers(rank_type, category, sort_by, direction)` | requires enum `rank_type` (`DAY_1`, `WEEK_52`, `PRE_MARKET`, …) — passing `"1d"` silently returns an empty list |
| `screener.get_most_active` / `get_52whl(NEW_HIGH…)` / `get_high_dividend` | ranked rows with price, volume, turnover_rate, relative_volume_10d, market_value, pe_ttm |
| `watchlist.get_watchlist` / `get_instruments` | **the operator's real Webull lists** — 21 lists; populated ones include ETFs (XLK…XLC sector set), Major Markets (SPY/QQQ/IWM/DIA…), AI, Minerals, Diversifying, Crypto ETFs, REIT, Currencies, Commodities, My Positions |
| `crypto_market_data.get_crypto_snapshot` / `get_crypto_history_bar` | **realtime crypto price + bid/ask and OHLC bars, no subscription** |
| `instrument.get_crypto_instrument`, `get_event_categories`, `get_futures_products` | crypto/event/futures reference data |

## Verified: blocked

| Call | Failure |
|---|---|
| `market_data.get_snapshot` / `get_quotes` / `get_history_bar` / `get_tick` | `403 MARKET_DATA_NOT_SUBSCRIBED — subscribe to STOCK QUOTES` |
| `option_market_data.*` | `403 MARKET_DATA_NOT_SUBSCRIBED — subscribe to US_OPTION` |
| `market_data.get_eod_bar`, `get_corp_action` | `404` (not deployed for this app/region) |
| `trade_instrument.get_tradeable_instruments`, `account_v2.get_account_position_details` | `404` |

Equity price history therefore stays on yfinance. That is fine — and it keeps the
split-adjustment invariant in `data_sources.fetch_ohlcv` as the single source of bar truth.

Streaming (`DataStreamingClient` MQTT quotes, `TradeEventsClient` gRPC order events) was not
probed: quote streaming needs the same gated subscription, and order-event streaming is
execution-oriented, which is out of scope for a slow-timeframe radar.

## Integration hygiene found during the audit (all four addressed — see Shipped below)

1. **`build_trade_client()` is rebuilt on every RPC** (`rpc_market.py` status/accounts/sync).
   Each construction runs `ClientInitializer` → a config HTTP round trip → token init. Cache one
   client per process instead.
2. **Background sync errors are silently dropped.** `handle_market_webull_sync` fires
   `asyncio.create_task(...)` and returns `startedAt`; a `fetch_snapshot` failure never reaches
   the UI. Contradicts the "do not swallow provider or storage errors silently" rule.
3. **The paid-subscription comment in `sync.py` is stale** — narrow it to realtime quotes.
4. New lanes should be new modules under `webull/` (`data_client.py`, `orders.py`,
   `watchlists.py`), not additions to `sync.py`.

## Shipped from this audit (2026-07-28)

1. **All-time P&L from fill history** — `webull/orders.py` walks every fill back to account open
   (cursor pagination, `last_client_order_id` alone); `webull/pnl.py` replays them FIFO into
   realized round trips, settles expired option lots, adds broker unrealized, and reconciles
   replayed open quantity against the snapshot. Surfaced as the **All-time P&L** panel, RPC
   `market.webull.orders.sync` / `market.webull.pnl.get`, and `uv run copenet webull pnl`.

   **Fill quantities are as-of-trade-day, so the replay MUST split-adjust open lots.** The first
   version did not, and reported +$985 on an account the Webull app shows at −$936. One
   unadjusted 1-for-20 reverse split (ETHU, ex-date 2025-04-09) matched 8 post-split shares
   against a pre-split $9.95 basis and turned a real −$1,273 loss into a phantom +$241 gain.
   Splits now come from `data_sources.fetch_splits` (raw corporate actions — NOT `fetch_ohlcv`,
   whose bars have already erased them), are stored with the fills, and apply per lot with a
   strict `lot_opened < ex_date <= fill_day` bound. A lot bought ON the ex-date already traded
   post-split; adjusting it doubles the position (XLK, 2025-12-05).

   Current live figure: −$812.15 (realized −$885.24, expired options −$100.00, vanished positions
   −$291.31, unrealized +$464.40) against the app's −$936.28. The remaining ~$124 is the seven
   2020 option fills the API returns with no execution price. Every held position now reconciles
   exactly with the broker's share count, which is the check that caught the bug.
2. **Watchlist import** — `webull/watchlists.py` + `WatchlistStore.replace_list()`; RPC
   `market.webull.watchlists.import`, the ⤓ Webull button on the watchlist panel, and
   `uv run copenet webull watchlists [--apply]`. Imports are a **pull**: Webull-side edits land
   here only when the import runs again.

Also done: the SDK clients are cached per process, and background lane failures are recorded and
returned in `market.webull.status.lastErrors` instead of vanishing into a discarded task.

## Candidate work, ranked

1. **Capital flow into fact packets** — differentiated daily flow signal the model reads have no
   access to today.
2. **Forward earnings** (`financials_alert` + `earnings_calendar` + `forecast_eps`) — CopeNet's
   Edgar lane is backward-looking; this adds "next print is in N days, consensus X".
3. **Analyst consensus + target price** on the ticker read.
4. **Sector breadth** from `get_market_sectors` for the macro panel.
5. **Discovery screeners** (52w high/low, most active, gainers/losers) for the morning sweep.
6. **Crypto lane** — free realtime snapshots + bars, a surface CopeNet has none of today.
