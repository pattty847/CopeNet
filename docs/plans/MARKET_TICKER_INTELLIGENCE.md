# market.ticker: compact intelligence packet

Status: implemented 2026-07-04, in response to live model feedback (GPT-5.5, via
`@XLK` mention) requesting a compact TA/RS/portfolio/thesis packet instead of a raw
OHLCV dump. Full feedback preserved in session context; this doc records what shipped
and what's intentionally deferred.

## What shipped

`MarketRuntime.ticker()` already computed a full `FeatureSet` (via `compute_features()`
in `features.py`) for the soft-bottoming insight card, then discarded everything except
the soft-bottoming fields. The fix was mostly **stop throwing the data away** — reshape
the existing FeatureSet into `TickerIntelligence` (`core/market/models.py`), a new
`intelligence` field on `TickerDetailPayload`:

- **trend** — MA stack, long-term trend direction/slope, distance/slope vs 10/30/40w MAs
- **momentum** — RSI-14, ATR%, ATR move multiple/percentile, volume vs average
- **returns** — 1w/4w/13w/26w/52w/YTD/3y
- **drawdown** — vs 52w and full-history highs, weeks since each
- **volatility** — 4w/13w/26w annualized, beta/corr vs VOO
- **relativeStrength** — RRG-style RS-ratio/momentum vs VOO, excess return 13w/26w, and
  benchmark verdict rows (now VOO + XLK + QQQ, was VOO + XLK only — additive, doesn't
  change the existing Market Monitor UI's verdict table)
- **structure** — range compression + shape (triangle-style consolidation)
- **rotation** — RRG quadrant for the specific symbol vs VOO (previously only computed
  for the fixed sector-ETF list on the dashboard; `compute_rrg_tail()` was already
  generic, just never called per-ticker)
- **portfolio** — Webull snapshot join if held, else static cost-basis fallback (mirrors
  the existing dashboard portfolio panel's join logic, now available per-symbol)
- **exposure** — best-effort ETF top-holdings + sector weights via `yfinance`
  `Ticker().funds_data` (see decision below); `None` for non-fund symbols or on any
  lookup failure — no partial/misleading data
- **thesis** — if a `market_thesis` memory item tagged `symbol:<SYMBOL>` exists, it's
  attached so the model can check current data against its own prior reasoning

The whole-dashboard `TickerDetailPayload.series` (OHLCV bars) is now trimmed to the
last N bars per timeframe by default (`bars`, default 60) in the **tool layer only**
(`core/tools/handlers/market.py`) — the `market.ticker.get` RPC the UI's candlestick
chart depends on is untouched, still full fidelity. The model can pass
`includeRawBars: true` for a genuine deep-history ask (e.g. backtesting).

## Decisions made explicitly (not left implicit)

**ETF holdings/exposure — best-effort via yfinance, not held for a data-source
discussion.** Verified live against `XLK` and confirmed `yfinance`'s `funds_data.
top_holdings`/`sector_weightings` work and raise a clean, catchable exception for
non-fund symbols (`AAPL` → `YFDataException`). No paid data source needed for v1;
honest `None` fallback everywhere else.

**Market thesis rides the existing memory system, not a new subsystem.** Added
`market_thesis` as a fifth `MemoryCategory` (`core/memory/store.py`). The model
proposes theses through the *existing* `memory.write` tool (updated docstring: title
`"<SYMBOL> thesis"`, tags must include `symbol:<SYMBOL>`, detail covers why/invalidation/
zones) — same draft → operator-approve flow every other memory category already has, no
new UI surface. `market.ticker` looks the thesis up by tag and attaches it automatically.

**Fixed while building this: memory tags never survived persistence.**
`MemoryRecord.to_json()` (via `dataclasses.asdict`) preserves `tags` as a `tuple`, but
`MemoryRecord.from_json()`'s `_string_list()` only accepted `list`, so every
`MemoryStore.upsert()` silently wiped tags back to `()` — for every memory category,
not just the new one. Fixed in `core/memory/store.py` (`_string_list` now accepts
`list | tuple`). This was a real, pre-existing bug; the market-thesis symbol lookup
would have silently never worked without it.

**"Read"/bull-case/bear-case text was deliberately NOT added to the packet.** The
feedback's `read.bullCase`/`bearCase`/`watchLevels` fields were skipped on purpose —
the packet stays factual/numeric so the model does its own reasoning over it, same
principle as "no news editorializing": give the model raw data, not backend-authored
conclusions.

## Explicitly deferred (needs a separate conversation)

- **News/catalyst adapter** (earnings, SEC filings, insider trades, analyst notes) —
  needs a trusted-source decision (raw filings/data over editorial commentary). Not
  started.
- **Explicit mention modes** (`@XLK quick`/`deep`/`news`) — not built. Per direct
  feedback, the model should infer depth/intent from the question itself rather than a
  rigid keyword parser; the richer `intelligence` packet is what makes that possible
  without UI-side mode-switching.
