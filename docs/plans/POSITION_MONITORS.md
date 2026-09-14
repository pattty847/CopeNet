# Positions and high-timeframe monitors

Implemented September 14, 2026.

## Position layer

`market.position.get` reads the selected account's saved Webull equity position and up to
2,000 filled-order aggregates. It never refreshes broker or market data. An exact account
fingerprint prevents cross-account reuse; old caches need one positions/fills sync. A newer
split in canonical price history hides stale position context until resync. Unknown currency,
cost, and P&L remain unknown. Options do not inherit the underlying equity's price or shares.

The ticker has a Position tab, average-cost line and snapshot P&L label. Optional shading
and buy/sell/short markers preserve the candle time axis. Order aggregates use their last
execution's session and original trade prices; they are not a lot ledger. Alt-crosshair or
an entered price estimates P&L using today's saved shares/cost, excluding fees. These are
scenarios, not historical account performance. Replay/comparison hide the position layers.
`account:position` contributes the displayed context through the existing capture path and
remains excluded unless chart-agent account context is enabled.

## Monitor semantics

- **Completed crossing:** the existing above/below crossing of two values on completed
  daily, weekly, or monthly US-equity candles; all registry indicators are available.
- **First interaction + close follow-up:** choose open/high/low/close and a direction.
  Equality counts. A forming candle is compared with a stable previous-completed-period
  reference. The first observed matching state emits a heads-up, then the completed candle
  emits confirmed/not-confirmed (or unavailable when the confirmation lacks warmup).
- The default confirmation compares the close with that completed candle's signal. A custom
  confirmation can compare other outputs, such as MAMA below FAMA. It replaces the default
  confirmation rather than silently adding an implicit second condition.
- A rule observes data only after its linked price scan. Set scan schedules to cover desired
  sessions and post-close checks. There is no continuous background quote subscription or
  guaranteed notification at the instant a price touches a line.
- Arming establishes a baseline and never reports an existing touch. A repeating monitor
  requires an observed reset. A one-shot monitor stops after its close follow-up.
- Events use stable IDs; one period cannot produce duplicate heads-ups. Missed periods,
  splits and revised history rebaseline transparently rather than inventing retrospective
  confirmations. Stale data never proves completion.

Rehearsal evaluates saved completed history with the same indicator registry. It reports
historical matches and confirmation results; it does not reconstruct intraperiod paths,
actual scan timing, historical account performance, or profitability. Rehearsal neither saves
rules nor sends notifications nor acquires market data.

## Telegram

Each rule separately opts into position context and chart images, alongside the existing
explicit destination/send authorization. Position context is frozen with its broker sync
time before the event enters the journal. A chart image is rendered from frozen candles and
comparison values, with a separate scale for the compared values and explicit source/phase
labels. It works without an open browser; it is not a screenshot of the operator workspace.

One photo and bounded caption are sent together. The outbox retains full evidence and the
image. Unknown send outcomes remain uncertain and never trigger a blind resend. Photo
render failures retain a text notification with a visible chart error. No real messages were
sent during implementation validation.

## Verification

- 606 frontend tests; TypeScript check and production/evaluator build passed.
- 304 focused backend/RPC tests; Python compilation passed.
- In-app browser, isolated synthetic server: position line/shading/markers, cursor and typed
  price scenarios, phone-width overflow check, custom confirmation editor, stored-history
  rehearsal, persisted Position tab, and non-held ticker exclusion.
- Live read-only SDK 3 positions/fill-history sync and cached-position RPC succeeded.
- Existing host restarted after confirming no in-flight sessions; `/health` returned 200.
- Product screenshot uses synthetic data only. Reproduce the isolated preview with
  `uv run python scripts/preview_market_position.py` after building the frontend.

Open orders, trade placement, paper trading, complete historical position valuation, editable
trade notes, and automatic monitor lifecycle tied to closing a position remain future work.
