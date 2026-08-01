# Daily price cache

## Why

Opening one ticker used to fire roughly eight yfinance requests: three for the D/W/M
candles, three more for the VOO/QQQ/XLK benchmarks, and two more when the P/E overlay
was on. The morning dashboard refresh does two per symbol across the whole universe.
None of it was cached — every view re-downloaded history that had not changed since 1999.

The fix is a durable, append-only daily cache that every price consumer reads from.

## The basis problem

Yahoo never serves truly raw prices. Two different bases hide behind one yfinance flag:

| call | `close` column |
|---|---|
| `auto_adjust=True` | splits **and** dividends |
| `auto_adjust=False` | splits only (`adj_close` carries both) |

Only one of those can be safely appended to. Every dividend retroactively shifts all
prior dividend-adjusted prices, so an append-only cache of `auto_adjust=True` bars
drifts at the seam between old and new rows, invisibly, forever. Split-only bars change
only when a split happens — a rare, discrete, detectable event.

So the cache stores **split-only daily bars plus the split and dividend histories**, and
derives whatever basis a consumer wants at read time.

> **Cache invariant: dividends never invalidate the cache; splits always do.**

This mirrors the append-only ledger already used for SEC facts. Stored data stays
immutable and checkable against the source; an adjustment bug is fixed by re-reading,
not by re-downloading. Rewriting bars in place would bake a bad factor in permanently
with no way to detect it.

## Shape

```text
yfinance Ticker.history(period="max", interval="1d", auto_adjust=False, actions=True)
  -> one request: split-only OHLCV + Dividends + Stock Splits
  -> PriceCache: <root>/prices/<SYMBOL>.json  (append-only daily bars + actions)
  -> price_history: resample to weekly/monthly, apply dividends on demand
  -> consumers
```

Weekly and monthly candles are **derived from daily**, not fetched separately. That is
one request instead of three and guarantees the three views agree with each other.
Weekly bars are anchored to the Monday of their week and monthly to the first of the
month, matching Yahoo's own convention so overlay timestamps keep lining up.

## Refresh

- No cache, or a split appeared that the cache does not know about → full `period="max"` rebuild.
- Otherwise → a small `period="6mo"` delta fetch, merged by timestamp with **overwrite,
  not append**. The newest bar is always provisional: during market hours Yahoo returns
  today's partial bar with the last trade as `close` and volume-so-far, so re-fetching
  the tail is what keeps today/this-week/this-month live.
- Younger than `max_age_seconds` → no network call at all.

Split detection rides along on the delta fetch. A `6mo` window carries any split inside
it, and anything older is already in the cache, so one request covers both jobs.

## Price bases

- `split_adjusted` — the stored basis. Correct for charts, pattern detection, drawdowns,
  and **trailing P/E**, where the numerator must be the price actually paid.
- `total_return` — dividends layered back on at read time. Correct for the backtester,
  where reinvested dividends are real money received.

The `auto_adjust=True` invariant in `AGENTS.md` still holds for `fetch_ohlcv`: it exists
because chart, backtester, and replay bars share one `MarketStore` cache key, and a
caller writing a different basis into it silently corrupts every other reader. The new
`fetch_daily_price_history()` is a separate function that never touches that cache, so
the hazard cannot occur. `tests/unit/test_market_data_contracts.py` pins both rules.

## Status

- [x] `fetch_daily_price_history()` — single split-only request
- [x] `price_history.py` — pure resample / dividend / merge transforms
- [x] `price_cache.py` — durable store and refresh orchestration
- [x] Wire the ticker chart path (`runtime.ticker`) and the VOO/QQQ/XLK benchmark reads
- [x] Wire the valuation path — historical P/E now divides split-only prices (AAPL Mar-2018 reads 17.0x against a real $41.23 close)
- [x] Wire the dashboard refresh — a universe sweep is 25 requests instead of 50, each a ~6mo delta after the first day
- [x] Watchlist quotes — a warm panel load is 0 requests; cold is capped at 2 concurrent
- [ ] Measure derived weekly/monthly against Yahoo's own aggregation and record the delta

## Remaining direct yfinance callers

Everything on the candle path reads the cache. Still direct, and fine as-is:
`search_symbols` (debounced typeahead, no history to cache), `fetch_key_stats` and
`fetch_fund_profile` (fast_info fields the cache does not hold), `fetch_split_history`
(cheap, and the cache exposes its own splits to callers that already hold a history),
plus `backtester.py` and `replay.py`, which take explicit user-initiated runs rather
than firing on render.
