# Market Tape Packet

The Market Tape Packet is the frozen, account-neutral observation layer behind CopeNet's daily
market interpretation. It answers a narrow but foundational question: **what market evidence did
the model actually see at that moment?**

## Contract

`market_tape.v1` is built from already-persisted public market data. Raw split-adjusted bars remain
the source of truth; the packet stores both a short normalized candle window and the derived state
used by the model so later research can reproduce or revise the derivation.

The stable instrument basket is intentionally small and role-based:

- VOO, QQQ, RSP, and IWM for broad trend, leadership, breadth, and size participation;
- HYG and LQD for credit appetite;
- TLT, VIX, DXY, and GLD for duration, volatility, dollar, and defensive pressure.

Each daily series carries 15 bars plus trailing returns, ATR-normalized candle geometry, distance
from moving averages, realized volatility, and relative volume. The packet also carries:

- weekly trend-state participation across public indexes and sectors;
- fast, default, and slow RRG position and motion when available;
- compact risk-plumbing relationships such as HYG minus LQD and RSP/IWM minus VOO;
- explicit coverage, missing-data, and incomplete-bar warnings.

Personal holdings, balances, watchlists, and portfolio conclusions are excluded. Optional portfolio
context remains a separate prompt section and must never alter the market observation itself.

## Point-in-time rules

- A packet includes no bar dated after `observedAt`.
- `observedAt` is taken from the persisted dashboard panels and is distinct from `generatedAt`;
  candle completeness is judged at observation time so a stale morning snapshot does not become a
  complete close merely because the model was invoked later.
- A same-day daily candle remains `complete: false` until 4:15 p.m. Eastern.
- The current weekly candle remains incomplete until Friday at 4:15 p.m. Eastern.
- `completedThrough` is the common completed-data watermark across available required instruments,
  not the freshest date found in any single series.
- The model prompt must treat partial candles as evolving evidence, never confirmed reversals.
- OHLC rows whose open or close falls outside high/low bounds retain their raw values, but candle
  geometry and gap derivations are suppressed and the affected symbol is named in data quality.

These rules apply equally to a live morning read and a historical replay. A future intraday lane may
create another packet at 3 p.m.; it must not rewrite the 9:46 a.m. observation.

## Persistence and interpretation

The latest packet is stored as `latest-market-tape.json`. Every edition is also archived under
`market-tapes/YYYY-MM-DD/<generatedAt>.json`, allowing multiple observations per day.

The full JSON contract is the research artifact. `market_tape_formatter.py` renders a smaller
analyst view for the one-shot market model call; it is a presentation of the saved contract rather
than a second calculation path.

## Extension boundary

New indicators should enter through a versioned feature definition with units, timeframe, lookback,
completion state, and derivation version. Saving every imaginable indicator now would duplicate
recoverable data and freeze accidental formulas. Preserve raw bars first; add derived features when
they are used by interpretation, replay, or a registered experiment.

The next research layers should build on archived packets rather than change this contract's job:

1. a regime ledger that records the model call, confidence, contradictions, and later outcomes;
2. a feature registry for WaveTrend and other candidate signals, including continuous distance,
   slope, closing speed, and binary event labels at explicit horizons;
3. walk-forward baselines before more expressive models;
4. calibrated probabilities and payoff distributions before any position-sizing experiment;
5. fractional-Kelly or stricter risk budgets only after calibration, costs, correlation, and maximum
   drawdown constraints are represented.

The packet is evidence infrastructure, not an alpha claim. Its first success criterion is that a bad
call can be reconstructed and diagnosed without guessing what the model saw.
