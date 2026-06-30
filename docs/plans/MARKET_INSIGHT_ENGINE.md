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
