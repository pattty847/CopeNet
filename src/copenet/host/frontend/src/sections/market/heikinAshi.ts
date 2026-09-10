import type { Ohlcv } from './types';

/** How the price series is drawn. Real OHLC, or the Heikin Ashi transform of it.
 *
 *  This is a *display* style, not a data source. `bars` stays the real series everywhere —
 *  indicators, price alerts, comparisons, the financial overlay and the agent capture all
 *  keep reading prices that actually traded. Only the candle series is redrawn. */
export type CandleStyle = 'candles' | 'heikin-ashi';

/** Heikin Ashi ("average bar") candles, derived from ordinary OHLC.
 *
 *    close = (o + h + l + c) / 4                 — this bar's own average
 *    open  = (previous HA open + previous HA close) / 2
 *    high  = max(h, open, close)
 *    low   = min(l, open, close)
 *
 *  The open reads the PREVIOUS synthetic bar, which makes the series recursive: start the
 *  calculation at a different bar and every value after it shifts. So it has to run over
 *  full history and be sliced afterwards — exactly the rule the indicator registry follows.
 *  Computing it on a range-sliced array would make the candles change shape when the
 *  operator switches 6M to 1Y, which is a chart lying about the past.
 *
 *  The previous open enters at weight one half, so a wrong seed decays by exactly half per
 *  bar (measured, not assumed — see the test). That is what makes a long warm-up sufficient
 *  rather than merely better: over full history the seed is below float precision.
 *
 *  It is causal — bar `i` depends only on bars `0..i` — so truncating the END, which is
 *  what replay does, leaves every retained value identical.
 *
 *  Volume is carried through untouched. It is a real measured quantity and the transform
 *  has nothing to say about it.
 */
export function heikinAshi(bars: readonly Ohlcv[]): Ohlcv[] {
  const out: Ohlcv[] = [];
  for (let index = 0; index < bars.length; index += 1) {
    const bar = bars[index];
    const close = (bar.o + bar.h + bar.l + bar.c) / 4;
    const previous = out[index - 1];
    // Seed: the first bar has no previous synthetic bar, so it opens at the midpoint of its
    // own real open and close. Every later value inherits from here.
    const open = previous ? (previous.o + previous.c) / 2 : (bar.o + bar.c) / 2;
    out.push({
      t: bar.t,
      o: open,
      h: Math.max(bar.h, open, close),
      l: Math.min(bar.l, open, close),
      c: close,
      v: bar.v,
    });
  }
  return out;
}

/** The candle rows to draw, aligned index-for-index with `bars`.
 *
 *  `history` is the full series the transform warms up over; `visible` is how many trailing
 *  bars the chart is showing. Returning the real bars for the plain style keeps the caller
 *  free of a branch and guarantees the two paths cannot drift in length. */
export function candleRows(history: readonly Ohlcv[], visible: number, style: CandleStyle): Ohlcv[] {
  const rows = style === 'heikin-ashi' ? heikinAshi(history) : [...history];
  return visible >= rows.length ? rows : rows.slice(rows.length - visible);
}
