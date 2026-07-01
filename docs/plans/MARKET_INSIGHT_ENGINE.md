# Market Insight Engine — Concept Note (Claude's take, for Codex review)

**Status:** discussion / vision alignment. No code. Patrick wants Claude + Codex to comment.
**Spawned from:** Patrick's note (2026-06-30) — extract rich derived facts from OHLCV to feed models;
backtest to refine the textual descriptions; "listen to the past, which is real."

---

## 1. The vision (Patrick's, captured faithfully)

Transform OHLCV into high-quality derived insights ("+X/-X over periods", textual descriptions of
price action like SOFI "soft bottoming") so models reason over rich, real data — not raw candles.
Validate against the real past (backtest). Iteratively refine the descriptions models are given.
Long-term: test model hypotheses against history; models "earn" their textual reads on real data.

## 2. Core principle (Claude's strong opinion)

**Deterministic feature extraction is the product. The LLM is the commodity on top.**

- LLMs are unreliable at arithmetic over long number series — feeding raw OHLCV invites hallucinated
  patterns and miscounting. Compute features in pandas (correct, testable, cheap), then hand the
  model **compact textual fact packets** it can *reason* over. This is the original "text packet"
  idea, scaled into a real feature library.
- Investment goes into the **feature catalog + the quality of its textual descriptions**, not the
  model. The model is swappable; the feature set is the moat.

## 3. The feature catalog (what to extract from OHLCV)

A named, documented, point-in-time-correct fact set per symbol/timeframe:

- **Returns:** over fixed windows (1w/1m/3m/6m/1y/YTD) + rolling; vs prior period.
- **Volatility:** realized vol, ATR + ATR percentile, vol regime (compression/expansion).
- **Trend / MA structure:** distance from key MAs, MA slopes, MA stacking; weekly-vs-daily alignment.
- **Drawdown:** depth, duration, time-since-high, recovery %.
- **Volume:** vs N-avg, up/down volume, OBV/accumulation-distribution.
- **Relative strength:** vs benchmark + sector, rolling RS, RS-momentum (already in the RRG).
- **Structure:** proximity to prior support/resistance, 52w position.
- **Shape descriptors (the frontier):** bottoming/basing/breakout/distribution/parabolic/
  capitulation — encoded as deterministic scores + plain-text labels. *"Soft bottoming"* = lower-lows
  stopped + higher-low confirmed + MA reclaim + momentum divergence + volume drying on declines.
  This is the high-value, interesting work.

## 4. Backtesting — the key reframe

**Backtest to calibrate HONESTY, not to chase alpha.**

- ✅ Calibrate the language to real base rates: "when we labeled X 'soft bottoming', it resolved up
  58% over the next 8 weeks (n=240)." Every adjective is anchored to history. This is the antidote
  to LLM-horoscope risk — the system earns its confidence.
- ❌ Do NOT optimize features to predict the past (curve-fitting; markets are adversarial +
  non-stationary). Calibrating *descriptions* ≠ optimizing *returns*.
- Mantra: "This setup went up 58% of the time" = honest. "This setup predicts +12%" = fiction.

## 5. The traps (keep us honest)

- **Lookahead / survivorship bias** — features must be computed point-in-time (only data available
  as-of the date). yfinance *adjusted* prices bake in future splits/divs — subtle lookahead; handle
  with care (consider raw + explicit adjustment).
- **Small n** — weekly/monthly setups over 5–10y give few independent samples. Report n; stay humble.
- **Non-stationarity** — regimes drift; base rates aren't constant. Prefer recent-weighted + full-
  history base rates side by side.
- **LLM arithmetic** — the model never computes features; it only reasons over pre-computed facts.

## 6. Proposed build sequence (each phase independently valuable)

- **A. Feature library** — `core/market/features.py`: OHLCV → named, documented, point-in-time facts.
  Pure + unit-tested. Foundation for everything (signals, RRG, briefing all consume it).
- **B. Fact-packet formatter** — features → compact text the model reads (per symbol + market-wide).
- **C. Point-in-time replay/backtest harness** — recompute features as-of historical dates, record
  realized forward returns, build **base-rate tables per pattern**. Calibrates the language.
- **D. LLM interpretation layer** — reasons over fact packets, *cites the base rates from C*, stays
  caveated. (This is the captured "one structured model call" upgrade to `synthesis.py`.)
- **E. (ambitious) Eval loop** — score the model's historical reads vs realized outcomes; point-in-
  time discipline mandatory. Dials in the descriptions over time.

## 7. Open questions (for Codex + Patrick)

1. **Data layer:** do we need a proper point-in-time OHLCV store (raw + adjusted) before backtesting?
   yfinance is fine for live; backtests need careful as-of handling. (Codex's call on storage.)
2. **Feature set v1:** which 10–15 features earn their place first? (Start with what the RRG/signals
   already compute + the shape descriptors.)
3. **Backtest scope:** which patterns get base-rate tables first? ("Soft bottoming" is the obvious
   flagship — Patrick's excited about it and it's well-defined.)
4. **Where base rates live:** computed offline + cached, or on-demand? Cost vs freshness.
5. **Eval ambition:** is the model-eval loop (E) a real near-term goal or a someday? (Claude leans
   someday — A→D delivers most of the value; E is research.)

## 8. Claude's verdict

This is a genuinely good system and the instinct is right: **rich derived facts + honest base-rate
calibration beats both raw-data-to-LLM and vibes-based commentary.** The feature library (A) is the
highest-leverage thing to build and makes every existing panel better immediately. The backtest
should calibrate *honesty*, which is the same honesty principle the whole Market Monitor already
runs on — this just gives it teeth from real history. Biggest risk is scope: A→B→D is shippable and
transformative; C (backtest) is where rigor matters most; E (evals) is research — sequence
accordingly and don't let the ambitious tail block the high-value head.

---

*Codex: your read? Especially §7.1 (point-in-time data layer) and §6.C (backtest harness design) —
those are backend architecture calls. And push back on anything here you think is wrong.*

---

## 9. Convergence — agreed design (Claude ⇄ Codex, 2026-06-30)

Codex reviewed §1–8 and the two takes converged. This section is the **agreed spec**; §1–8 above is
the original framing. Patrick to greenlight when sober.

### Module layout (`src/copenet/core/market/`)
- `data_sources.py` — vendor fetch ONLY (raw OHLCV + corporate actions + metadata). No feature math.
- `history_store.py` (or upgraded `store.py`) — durable historical bars/actions/snapshots.
- `prices.py` — point-in-time query API.
- `features.py` — pure feature extraction from a supplied snapshot. **Typed numeric facts** (units,
  lookback, timeframe, as_of) — NOT strings.
- `formatter.py` — features → compact text fact packets (the only place text is produced).
- `replay.py` — historical replay harness (boring orchestration; NO feature logic of its own).
- `base_rates.py` — versioned calibration table builder/reader.

### Storage — DuckDB (or SQLite), not JSON, for history
Indexed by `symbol, timeframe, bar_date, as_of, basis, vendor, ingested_at, feature_version`.
- Store **raw** bars as observed (o/h/l/c/v); corporate actions (splits/divs) **separately**;
  ingestion metadata (`fetched_at`, `source`, payload hash).
- Compute adjusted views ourselves at query time (or materialize with explicit `adjustment_as_of`).
- **The contract:** `get_price_frame(symbol, timeframe, as_of, basis="raw|split_adjusted|total_return_adjusted")`
  — includes only bars with `bar_date <= as_of` and adjustments whose ex/effective date `<= as_of`.
  A 2026 split must NOT alter the 2024 series when replaying 2025. This is THE lookahead guard.
- **v1 ingestion (Claude):** yfinance `auto_adjust=False` (raw bars) + `.splits`/`.dividends`
  (actions) → reconstruct adjustments ourselves. Achievable now.
- **Provenance (Claude):** stamp each bar `vendor_snapshot = as_observed | backfill`. Backfilled
  history is "best available archive," not a true point-in-time snapshot — keep it queryable, never
  pretend otherwise.

### Live ⇄ replay: identical code path (the no-skew rule)
```
live:   Store -> PriceSnapshot(as_of=today)      -> FeatureExtractor -> Formatter -> LLM
replay: Store -> PriceSnapshot(as_of=historical) -> SAME extractor   -> SAME fmt  -> [label forward returns] -> base_rates
```
- The **snapshot is the only thing that changes** between live and replay.
- **Claude's enforcement upgrade:** the `PriceSnapshot` is *physically incapable* of returning a bar
  after `as_of` — leakage is structurally impossible, not just discouraged.
- Forward-return labeling is a **separate phase**; realized outcomes NEVER enter the extractor or
  formatter.
- **Base rates** = offline-built, cached, **versioned artifacts** keyed by
  `feature_catalog_version, pattern_id, universe_id, timeframe, horizon, benchmark, sample window,
  generated_at`. Production briefings READ cached tables (on-demand only for dev/drill-down).

### Feature catalog v1 (typed numeric)
Returns (1w/4w/13w/26w/52w/YTD) · benchmark excess return (VOO + sector) · beta + correlation
(26w/52w) · realized vol (4w/13w/26w) · ATR% of price + latest move in ATR units · ATR percentile /
vol regime · distance from 10/30/40w MAs · MA slopes · MA stack/trend regime · 52w drawdown depth ·
drawdown duration / time-since-high · 52w position percentile · volume vs 20-avg · up/down volume
(accum-distribution proxy) · RS ratio + momentum (reuse RRG).
**Plus data-quality features (Codex's catch):** history depth, stale-bar age, volume availability,
basis availability, symbol-mapping confidence — so the model knows when facts are weak.
**Shape descriptors:** ship exactly ONE flagship in v1 — `soft_bottoming_score`, decomposed +
auditable (lower-lows-stopped · higher-low · short-MA reclaim · drawdown stabilized · RS improving ·
decline-volume drying · optional momentum divergence). Defer parabolic/capitulation/distribution/
breakout until the pipeline proves it calibrates ONE descriptor honestly.

### Calibration discipline (resolved)
- DO measure: forward-return distributions, max adverse excursion, benchmark-relative outcomes,
  false-positive rates, regime splits. That IS calibration.
- DON'T: parameter-mine thresholds until the backtest looks rich (overfitting).
- **Claude addition — pre-register** the descriptor + horizon before testing (e.g. `soft_bottoming`
  / 8-week). No fishing across 50 descriptor×horizon combos and reporting the winner.

### Agreed sequencing
`A1 typed feature library` → `C1 tiny replay + base-rate path (1 descriptor, 1 horizon)` ∥ `B fact
packets` → `D LLM interpretation (cites earned base rates)` → `A2/C2 richer shape descriptors` →
`E model-eval research`. **D must not narrate historical tendencies before C1 exists.**

### Open for Patrick (greenlight items)
1. OK to move historical market data to **DuckDB** (keep JSON for the latest-dashboard payload)?
2. Confirm flagship descriptor + horizon to pre-register first: **`soft_bottoming` / 8-week**?
3. Scope of v1 universe for base rates: just the watchlist, or a broad universe for bigger n?

---

## 10. BUILT overnight 2026-06-30 (autonomous, grounded)

Codex CLI was unavailable on PATH, so Claude executed the converged §9 spec solo (Codex's review is
already baked into §9). Shipped + verified live + tested:

- **A1 — feature library** (`features.py`, PR #13): typed numeric FeatureSet (returns/vol/ATR/MA/
  drawdown/RS/RSI + data-quality) + flagship `soft_bottoming` (decomposed, pre-registered threshold
  0.6). Pure + point-in-time (slice-independence test). 5 tests.
- **C1 — calibration** (`replay.py` + `base_rates.py`, PR #14): point-in-time replay reusing the
  exact live feature path; episode de-dup; split-adjusted; forward returns in a separate label phase.
  **Calibrated: soft_bottoming/8w resolved up 54% (median +1.6%, n=611, 2019–2026), beats VOO only
  47%, works better in bear (61%) than bull (51%).** Cached versioned artifact. Script:
  `scripts/run_base_rate_calibration.py`. 3 tests.
- **Surfacing** (PR #14 + #15): ticker detail shows soft_bottoming + decomposed checklist + base
  rate ("a base rate, not a forecast"); dashboard "Soft Bottoming Watch" strip flags watchlist names
  (SOFI + TSLA live). 442 tests pass total.

**Deliberately NOT built (needs Patrick's greenlight):**
- **D — LLM interpretation.** Per §9 sequencing, D follows C1 (now done). But D spends provider
  quota and produces the *model's opinion* Patrick explicitly wants to SHAPE. Building it
  autonomously would make a product/cost call that is his to own — so it stops here, by design.
  Next session: shape the prompt + structured-output schema together, then wire `synthesis.py` →
  frontier model that reasons over the fact packets + cites these base rates.
- **DuckDB point-in-time store** (§9 greenlight #1): C1 runs in-memory on yfinance split-adjusted
  history, which is honest for pattern *shape* but not a true vendor as-of archive. The DuckDB
  store (raw bars + actions + `get_price_frame`) is the rigor upgrade — still pending greenlight.

**Open greenlight items (unchanged):** DuckDB store? confirm `soft_bottoming/8w` pre-registration
(done as the v1 flagship)? base-rate universe scope (current: watchlist + drawdown basket, n=611).

---

## 11. Phase B+D SHIPPED 2026-07-01 (PR #17) — greenlit by Patrick

Operator design: **GPT-5.5**, two lanes — automatic whole-market read per refresh + on-demand
per-ticker read via a button on the detail page. Built: `fact_packets.py` (B), `interpretation.py`
(D: prompts w/ honesty rails, JSON schemas, tolerant parsing, one-shot provider invocation),
`runtime.interpret`, `market.interpret`/`market.read.get` RPCs (background — model calls exceed the
15s ws timeout), reads persisted under `reads/`. Frontend: model read takes over the briefing hero
(GPT-5.5 badge), regime hover reasoning, RRG rotation note, spec-lane comment, model thesis-killers,
per-ticker read panel (bull/bear/change-my-mind/confidence/key facts). Verified live: model quotes
base rates verbatim and stays humble ("only modest", "not decisively bullish"). 448 tests.
Remaining from §9: DuckDB point-in-time store (greenlight pending), A2/C2 richer descriptors, E evals.
