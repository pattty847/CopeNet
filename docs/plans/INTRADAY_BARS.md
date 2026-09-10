# Intraday Bars — Plan

**Status:** Phases 1-3 built. Session toggle, VWAP and volume profile not started.
**Written:** 2026-09-09
**Supersedes nothing.** Implements the store that `MARKET_SENTINEL_ALERTS.md` Phase 1 has
been blocked on since 2026-07-29 ("Dedicated intraday store with explicit vendor and
adjustment basis").

## 1. What this is for

Sub-day candles on the ticker chart, fetched on demand and cached locally. The chart is the
first consumer, not the only one — the store is the missing foundation under four features
that are already specified and blocked:

| Blocked on intraday | Where it is written down |
|---|---|
| Real session VWAP | `CHART_INDICATORS.md` — "the finest bar here is daily, where a session VWAP is identical to the bar's own typical price and measures nothing" |
| Shadow sentinel (Phase 1) | `MARKET_SENTINEL_ALERTS.md` §2 |
| Volume profile with a real POC | measured 2026-09-09; daily bars can only produce Volume-by-Price |
| Relative volume, opening range, gap statistics | `MARKET_SENTINEL_ALERTS.md` Phase 3 |

Design for the store, not for the chart. The chart is one reader.

## 2. Measured vendor limits

AAPL, 2026-09-09, yfinance, regular session only. Every number below was measured, not
quoted — re-measure with `scripts/market_data_probe.py` before trusting it later.

| Interval | Bars / session | Window Yahoo allows | Max rows | Per-request cap |
|---|---:|---|---:|---|
| `1m` | 390 | **30 days** | ~8,190 | **7 days** (~1,950 rows) |
| `5m` | 78 | 60 days | 3,276 | whole window |
| `15m` | 26 | 60 days | 1,092 | whole window |
| `30m` | 13 | 60 days | 546 | whole window |
| `1h` | 7 | **730 trading days** (~2.9 calendar years) | 5,073 | whole window |
| `1d` | 1 | unbounded | — | whole window |

Beyond each window Yahoo refuses explicitly — *"1m data not available … must be within the
last 30 days"* — rather than silently truncating. That is a usable signal: the error text
carries the real limit, so the ceiling can be discovered rather than hardcoded and left to
rot.

### Two findings that decide the architecture

**`1m` is the only interval that needs paging.** It is capped at 7 days per request but
allows 30 days total, so full depth is 4–5 paced requests. Everything else returns its
entire available window in a single call. So "get more history" is a `1m` affordance, not a
general mechanism — do not build a general one.

**`15m` and `30m` are strictly worse than `5m` on this vendor.** Same 60-day ceiling, fewer
bars. Fetching them buys nothing that resampling `5m` does not already give, at the cost of
another request and another cache entry.

## 3. Architecture

### Native grains, derived intervals

Fetch three grains and derive the rest, exactly as the daily cache stores D and derives W/M:

```
fetched:   1m ──► 2m 3m 5m* 10m 15m 20m 30m      (*5m also fetched: deeper window than 1m)
           5m ──► 10m 15m 30m
           1h ──► 2h 4h
```

Rules:

- **A derived interval must divide its grain exactly.** 5m→15m is legal; 5m→7m is not.
- **Prefer the deepest grain that satisfies the request.** 15m over the last week can come
  from `1m` or `5m`; use `5m`, because the answer is identical and `5m` reaches further back.
- **Never derive across a session boundary.** A 4h bucket does not span two days.

This is the same shape as `resample_bars`, which groups dailies by `_period_start`. That
function is date-keyed and cannot be reused as-is; generalise it to take a bucket function
so one roll-up serves both lanes rather than two drifting copies.

### Bucket anchoring

Anchor intraday buckets to the **session open**, not the wall clock. Yahoo already does:
its hourly bars run 09:30, 10:30 … 15:30 — seven per session, the last a 30-minute stub.
Matching the vendor keeps derived bars aligned with fetched ones.

This matters for the reason `resample_bars` documents for weeklies: financial overlays and
markers snap to candle timestamps, and a bar on an unexpected boundary injects a new slot
into the chart's index-based time axis instead of landing on an existing candle.

### Storage

A store of its own. `MARKET_SENTINEL_ALERTS.md` §3 rule 2 already forbids intraday entering
the `(symbol, timeframe)` MarketStore, and rule 3 fixes the key: **vendor, symbol, interval,
timestamp, session, adjustment basis.**

- **Split-only, like the daily cache.** `auto_adjust=True` hides two adjustments behind one
  flag, and dividend-adjusting retroactively shifts every prior price — which drifts an
  append-only cache invisibly at the seam. Over a 30-day `1m` window that is at most one
  ex-date; over a 730-day `1h` window it is several. One canonical basis across the system.
- **Reuse the daily cache's split fingerprint to invalidate.** A split inside the window
  corrupts an append-only intraday cache exactly as it corrupts a daily one, and the
  detection already exists — do not write a second mechanism.
- **Store both sessions; tag every bar with its own.** An earlier draft of this plan said
  regular-session only, on the grounds that zero-volume bars invite a VWAP built on nothing.
  That was wrong, and wrong in an interesting way: zero volume is *mathematically neutral*
  for every volume-weighted calculation. A zero-volume bar contributes nothing to either side
  of a VWAP, adds no row to a volume profile, and moves OBV not at all. Those indicators do
  not break on extended bars — they ignore them, correctly.

  The real hazard is elsewhere. Session mode changes **what every price indicator means**,
  because it changes the bar count: 390 minutes a session regular, ~960 with extended. An
  RSI(14) on extended-inclusive 5m data is simply a different indicator from the same RSI on
  regular-session data, and nothing in the output says so. Relative volume is worse — it
  divides by a baseline that is structurally zero overnight.

  **Operator decision, 2026-09-09: draw every candle, and let volume simply be absent
  overnight.** That resolves the concern above rather than dodging it — the meaning change is
  only dangerous when it is *silent*, and an extended-hours candle is visibly on the chart.
  Volume gaps to zero overnight and picks up the next session, which is what the instrument
  actually did.

  So session is a **query mode** stored on the bar and present in the cache key (which is why
  `MARKET_SENTINEL_ALERTS.md` rule 3 put it there), defaulting to *all sessions*. The toggle
  restricts to regular hours for anyone who wants indicators free of thin overnight bars. The
  mode belongs in the chart chrome and in the agent capture, not in a settings menu.

  Note the fetch consequence: Yahoo defaults to regular session only, so extended coverage
  needs `prepost=True`. That is about 2.4x the rows (the July probe measured 4,761 extended
  vs 1,949 regular one-minute bars over 5 days), which multiplies both the cache size and
  every bars-per-viewport figure in the table above.

  Extended-hours *volume* remains unusable regardless: the 2026-07-29 probe found nonzero
  extended volume on 4 of 2,815 one-minute AAPL bars. Relative volume and any
  volume-normalised statistic stay regular-session-only until a probe says otherwise.
- **Bars are revised.** The vendor rewrites recent bars. Refresh with an overlap and let
  later values replace earlier ones; never blind-append.

### Fetching

- **Lazily, never on page load.** The daily/weekly/monthly series ship inside `ticker.detail`
  because they all derive from one cached daily history. Intraday cannot: it is a separate
  fetch per interval, so it gets its own RPC and is requested when an intraday timeframe is
  actually selected.
- **On CopeNet's existing fetch pace.** `COPNET_MARKET_FETCH_PACE` already paces yfinance.
  Intraday adds volume to that lane, not a second policy.
- **A forming bar is not a closed bar.** The current session's last bar is still moving.
  Mark it, and never let a completed-candle consumer (alerts, base rates) read it. The daily
  lane already draws this line in `completed_candles`.

## 4. How much to fetch

Lightweight Charts' default `minBarSpacing` is 0.5px, so a ~1,300px chart shows about
**2,600 bars** fully zoomed out. `CHART_BAR_LIMITS[DAILY]` is `2_600` — the daily transport
limit already *is* one viewport. Intraday inherits the convention.

| Interval | First pull | ≈ viewports | More available? |
|---|---:|---:|---|
| `1m` | 7 days ≈ 1,950 | 0.75 | yes — page to 30 days (~8,190) |
| `5m` | 60 days = 3,276 | 1.26 | no, that is the ceiling |
| `15m` | derived from 5m = 1,092 | 0.42 | no |
| `30m` | derived from 5m = 546 | 0.21 | no |
| `1h` | 730 sessions = 5,073 | 1.95 | no, that is the ceiling |

So only `1m` gets a **Load earlier** control. Every other interval arrives complete, and the
UI should say so rather than offering a button that cannot do anything.

## 5. Timeframe selector

- **Pinned in the toolbar:** the operator's chosen few, reorderable, persisted like the
  indicator layout and the candle style.
- **Dropdown** for everything else, grouped intraday / daily / weekly-monthly, each row
  carrying its real depth ("5m · 60 days") so the ceiling is visible at the point of choice
  rather than discovered as an empty chart.
- **Custom intervals** are allowed only where they divide a native grain (§3). Offering `7m`
  and then silently rounding it would be worse than not offering it.
- **Unavailable is a state, not an empty chart.** `^VIX` supplied no volume at all in the
  probe; an index has no intraday volume to profile. Say `data_unavailable` with the reason,
  per `MARKET_SENTINEL_ALERTS.md` §3 rule 5.

## 6. Consequences worth foreseeing

- **Replay gets an intraday cursor for free** — it truncates `bars`, and it does not care
  what a bar is.
- **Indicators keep working, but `barsPerYear` must be extended.** It is a hardcoded
  `'D' | 'W' | 'M'` union returning 252/52/12. A 5m chart has 78 × 252 = 19,656 bars a year,
  and annualisation scales by the square root — so historical volatility would read
  **√78 ≈ 8.8× too low** until intraday entries are added. Every other indicator is
  interval-agnostic; this one is not, and the type will not catch it because `ChartTimeframe`
  has to widen anyway.
- **Chart agent capture** must carry the interval and its adjustment basis, or a model reads
  5m bars believing they are daily.
- **The daily cache stays canonical for anything long-horizon.** Base rates, backtests and
  financial overlays are daily and should not be quietly re-pointed at a 60-day window.
- **Cache size, measured rather than estimated.** The estimate here was 500 KB for a
  symbol's 1m history; the real figure is **2.8 MB**, because it forgot that extended hours
  is 2.4x the rows and that JSON at full float precision costs ~145 bytes a bar. AAPL at
  full depth across all three grains is **5.2 MB** (1m 19,136 bars, 5m 8,064, 1h 8,272). A
  60-symbol watchlist would be ~300 MB, not 30. Still workable on a laptop, but the prune
  policy is nearer than it looked, and rounding stored prices would be the cheap first cut.

## 7. What this is NOT a foundation for

The windows are short, and that bounds the ambition honestly:

- `1m` reaches 30 days. `5m` reaches 60. `1h` reaches 2.9 years.
- So intraday is a **recent-context** substrate, not a research one. Base rates, backtests,
  point-in-time replay and the financial overlays stay daily, and should — repointing any of
  them at a 60-day window would quietly shrink the sample that makes them mean anything.
- Yahoo intraday is also the least official thing CopeNet consumes. The daily lane is robust;
  this one should be assumed to break someday, which is another reason the store is keyed by
  vendor.

## 8. Phasing

1. ~~**Store + fetch + resample**, tested offline against fixtures. No UI.~~ **Done.**
   `core/market/intraday/` — `intervals.py` (the grain algebra), `resample.py` (session
   anchoring), `store.py` (cache + session derivation), `fetch.py` (paged vendor lane).
   `fetch_pace.py` moved the shared yfinance budget out of `runtime.py`, because the intraday
   lane spends from the same one. Verified live: 15m resolves to the 5m grain, 384 bars in one
   request, 55 KB cached, re-merge idempotent, 128 derived 15m bars on :00/:15/:30/:45.
2. ~~**RPC + one hardcoded interval** on the chart.~~ **Done.** `IntradayService` plus
   `market.intraday.get` / `market.intraday.intervals`.
3. ~~**Timeframe selector** — pinned, dropdown, `1m` paging.~~ **Done.** Pinned strip with a
   dropdown carrying each interval's real depth; ranges follow the lane (`1D/5D/1M/MAX`
   intraday); `Load earlier` appears only on `1m`. The session toggle is NOT built — the
   store and the RPC take a session and default to `all`, but nothing in the UI switches it
   yet.

Then **stop and use it**. Whether 60 days of 5m is enough depends entirely on how the chart
actually gets read, and neither the plan nor the vendor can answer that. Only after that:

4. **Session VWAP**, the smallest real consumer, which validates the session anchoring.
5. **Volume profile**, which is what prompted this.

Stop after 1 if the vendor limits turn out worse than measured. The store is the valuable
part; the chart is a reader.
