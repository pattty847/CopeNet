# Market Sentinel Alerts — Architecture and Experiment Log

**Status:** Phase 1 partial — durable daily-close price crossings ship; intraday lane remains in Phase 0

**Started:** 2026-07-29

**Product goal:** Deterministic, context-aware market surveillance for one operator, with
durable events and noise-controlled Pulse/Telegram delivery.

## 1. Product boundary

The Market Sentinel is not a day-trading terminal. It watches explicitly armed symbols and
market conditions so the operator can focus on work and school without missing a meaningful
change.

Canonical flow:

```text
Market data
  → deterministic rule evaluation
  → durable alert event
  → optional context/model annotation
  → Pulse / Telegram / dashboard
```

The deterministic event remains canonical. Model annotation may explain importance but cannot
decide whether a mathematical crossing occurred.

## 2. Phase plan

### Shipped first vertical slice

- The ticker chart's **Add alert** control enters a crosshair placement mode and creates a
  one-shot `above` or `below` price rule.
- Rules persist under the operator's Market directory; cancelled and triggered rules remain
  durable, and trigger events append to JSONL.
- Active levels render as dashed chart price lines.
- Evaluation uses the canonical split-adjusted daily close during the unattended morning sweep
  and operator-triggered full/signal refreshes. A crossing creates a Pulse item.
- The UI explicitly says **daily close**. Intraday polling, Telegram, cooldown/rearm, indicator
  rules, and composite conditions are not implied by this slice.

### Phase 0 — specification and data proof (completed foundation)

- Measure actual yfinance intraday/session/volume behavior.
- Keep raw probe data local; commit only code and compact findings.
- Define forming-versus-closed bar semantics.
- Verify timestamp, extended-hours, adjustment, and revision behavior.
- Establish conservative request pacing and backoff.
- Evaluate free/affordable secondary data sources without depending on them.

### Phase 1 — shadow sentinel

- Dedicated intraday store with explicit vendor and adjustment basis.
- Fixed price-level, zone, moving-average-close, and regular-session VWAP rules.
- Durable rule versions, evaluation state, and events.
- Manual evaluation plus historical replay.
- No Telegram; report what would have fired.

### Phase 2 — trusted internal delivery

- Market-session-aware scheduler.
- Pulse delivery.
- Evaluation-history and "why did/didn't this trigger?" UI.
- Cooldown, hysteresis, rearm, snooze, expiration, and scan aggregation.

### Phase 3 — intelligence and phone loop

- Relative volume and relative strength.
- Model-proposed transparent rule compilation.
- Bounded model event annotations.
- Telegram delivery by severity.
- Alert bundles.

### Later differentiation

- Research Lab thesis conditions.
- SEC/evidence and portfolio-aware rules.
- Composite conditions and sequences.
- Watchlist rankings and alert-quality calibration.
- Better intraday vendor when value justifies cost.

## 3. Load-bearing data rules

1. Every yfinance request remains `auto_adjust=True`.
2. Experimental intraday data never enters the existing `(symbol, timeframe)` MarketStore cache.
3. A future intraday store must key bars by vendor, symbol, interval, timestamp, session, and
   adjustment basis.
4. UI/model reads consume local stored bars; they do not independently call the vendor.
5. Unsupported or incomplete data produces an explicit `data_unavailable` state.
6. Regular-session and extended-hours volume observations are measured separately and per
   interval; the probe does not declare them usable for VWAP.
7. Extended-hours VWAP is disabled unless a probe proves trustworthy extended-hours volume.

## 4. Conservative yfinance request policy

- Only explicitly armed intraday symbols are polled.
- Start with sequential requests (`threads=False`, concurrency 1).
- Start with at least one second between requests and add scheduler jitter.
- Prime history once; incrementally refresh with an overlap so revised bars replace prior values.
- Do not request the same symbol/interval inside its freshness window.
- Do not poll when the relevant market/session is closed.
- Stop the vendor lane on a rate-limit response; use progressively longer backoff.
- Track request count, latency, row count, newest timestamp, errors, and bar revisions.
- Never evade rate limits through proxy rotation or retry storms.

No dependable public Yahoo request quota exists. These are conservative operating rules to
measure and refine, not a guarantee against throttling.

## 5. Probe tool

Run:

```bash
uv run python scripts/market_data_probe.py AAPL VOO SOFI '^VIX'
```

Default requests per symbol:

- `1m` / `5d`
- `5m` / `1mo`
- `1h` / `1mo`

The tool:

- forces split-adjusted data;
- performs sequential, paced downloads;
- applies an explicitly unverified US-equity assumption: 04:00–09:30 ET premarket,
  09:30–16:00 ET regular, and 16:00–20:00 ET after-hours;
- measures volume-field presence, reported-value coverage, nonzero coverage, and sample
  timestamps per assumed session;
- reports duplicates and empty responses;
- keeps only compact sample bars;
- writes summaries beneath `~/.copenet/market/probes/`.

Bulk vendor bars are not committed to the repository.

## 6. Experiment log

### 2026-07-26 — manual AAPL feasibility probe

Environment: yfinance 1.5.1, split-adjusted, America/New_York.

| Request | Rows | First bar | Last bar |
|---|---:|---|---|
| 1m regular, 5d | 1,949 | 2026-07-20 09:30 ET | 2026-07-24 15:59 ET |
| 1m extended, 5d | 4,761 | 2026-07-20 04:00 ET | 2026-07-24 19:59 ET |
| 5m extended, 1mo | 4,032 | 2026-06-25 04:00 ET | 2026-07-24 19:55 ET |
| 1h extended, 1mo | 357 | 2026-06-25 04:00 ET | 2026-07-24 19:00 ET |

Findings:

- AAPL supplied regular, premarket, and after-hours prices.
- Regular-session volume was populated.
- Sampled premarket and after-hours bars reported zero volume.
- A vendor-derived regular-session VWAP is mathematically computable from these bars; fidelity
  against consolidated market volume remains unverified.
- Extended-hours price-level/gap rules appear feasible.
- Extended-hours VWAP and relative-volume rules remain disallowed pending contrary evidence.
- Five-minute bars are the preferred Phase 1 substrate; one-minute ingestion is not yet
  justified.

### 2026-07-29 — reusable four-symbol probe

Command:

```bash
uv run python scripts/market_data_probe.py AAPL VOO SOFI '^VIX'
```

Environment: yfinance 1.5.1, split-adjusted, America/New_York, 12 sequential requests with
one-second pacing.

| Symbol | 1m / 5d | 5m / 1mo | 1h / 1mo | Regular volume observation | Assumed extended-window prices |
|---|---:|---:|---:|---|---|
| AAPL | 4,764 rows | 4,032 rows | 357 rows | populated | yes |
| VOO | 4,712 rows | 3,969 rows | 357 rows | populated | yes |
| SOFI | 4,503 rows | 4,029 rows | 357 rows | populated | yes |
| ^VIX | 3,874 rows | 3,376 rows | 303 rows | absent | yes |

Extended-volume finding:

- AAPL reported nonzero extended-session volume on only 4 of 2,815 one-minute bars.
- VOO reported it on only 4 of 2,762 one-minute bars.
- SOFI reported it on only 3 of 2,553 one-minute bars.
- Every sampled 5-minute and hourly extended-session bar reported zero volume.
- The isolated one-minute values are consistent with boundary/closing-auction bars, not
  trustworthy extended-hours volume coverage.
- The probe records these interval-specific counts without declaring the volume usable.

Decisions:

- A Yahoo-bar regular-session VWAP is mathematically computable for AAPL, VOO, and SOFI.
  Accuracy against an official/consolidated VWAP remains unverified, so production eligibility
  is still open.
- Extended-hours VWAP and relative-volume rules remain disabled.
- Extended-hours price highs/lows, gaps, zones, and crossings remain candidates.
- ^VIX supplied no volume in this probe; volume-based rules must treat its volume input as
  unavailable unless another source proves otherwise.
- A single US-equity session assumption is insufficient for every instrument: ^VIX returned
  bars outside the equity 04:00–20:00 window. It also cannot model holidays or early closes.
  Future capability records need an asset/exchange calendar profile rather than silently
  treating wall-clock labels as authoritative.
- Volume evidence stays interval-specific and distinguishes a missing field, reported zeros,
  isolated nonzero rows, and dense nonzero coverage.

### 2026-07-30 — scheduled Yahoo WebSocket session

Planned window: 09:20–16:10 America/New_York. Symbols: AAPL and SPY.

The bounded probe records decoded price messages separately from connection events. It has a
hard stop, at most five reconnects, progressively longer randomized backoff, and an exact-date
guard. Evidence includes populated fields, message counts, vendor timestamps, receive lag,
disconnect exceptions, HTTP status when exposed, WebSocket close code/reason, and reconnect
attempts. Stream messages remain experimental quote observations rather than canonical candles.

## 7. Open Phase 0 questions

- Does extended-hours volume remain zero across liquid stocks, ETFs, volatile holdings, and
  indexes?
- How often does Yahoo revise forming and recently closed bars?
- How stale is the newest bar during regular and extended sessions?
- What overlap is sufficient for reliable incremental upserts?
- Are missing bars true no-trade intervals or vendor gaps?
- How does behavior change across holidays and early closes?
- Can a free secondary quote/WebSocket source improve timeliness without mixing canonical bar
  histories?
