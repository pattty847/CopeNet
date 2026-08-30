// Shared synthetic bar builders for the indicator tests.
//
// Deliberately deterministic: a seeded LCG rather than Math.random, so a failure is
// reproducible from the test name alone and a flaky assertion is impossible.

import type { IndicatorBar } from '../src/sections/market/indicators/types';

const DAY = 86400;

export function barsFromCloses(closes: number[], volume = 1_000): IndicatorBar[] {
  return closes.map((close, i) => ({
    t: 1_700_000_000 + i * DAY,
    o: i === 0 ? close : closes[i - 1],
    h: Math.max(close, i === 0 ? close : closes[i - 1]) * 1.01,
    l: Math.min(close, i === 0 ? close : closes[i - 1]) * 0.99,
    c: close,
    v: volume,
  }));
}

/** Explicit OHLC, for fixtures where the exact high/low matters. */
export function barsFromOhlcv(rows: [number, number, number, number, number][]): IndicatorBar[] {
  return rows.map(([o, h, l, c, v], i) => ({ t: 1_700_000_000 + i * DAY, o, h, l, c, v }));
}

export function constantBars(length: number, price = 100, volume = 1_000): IndicatorBar[] {
  return Array.from({ length }, (_, i) => ({
    t: 1_700_000_000 + i * DAY,
    o: price,
    h: price,
    l: price,
    c: price,
    v: volume,
  }));
}

export function rampBars(length: number, start = 100, slope = 1): IndicatorBar[] {
  return barsFromCloses(Array.from({ length }, (_, i) => start + i * slope));
}

/** A ramp where the close IS the extreme of its own bar — the close equals the high while
 *  advancing and the low while declining.
 *
 *  `rampBars` pads the high 1% above the close, which is realistic but means the close never
 *  actually touches the window extreme. That distinction is invisible for a moving average
 *  and decisive for Stochastic and Williams %R, whose entire output is "where did the close
 *  land inside the range". */
export function edgeRampBars(length: number, start = 100, slope = 1): IndicatorBar[] {
  return Array.from({ length }, (_, i) => {
    const close = start + i * slope;
    const open = i === 0 ? close : start + (i - 1) * slope;
    return {
      t: 1_700_000_000 + i * DAY,
      o: open,
      h: Math.max(open, close),
      l: Math.min(open, close),
      c: close,
      v: 1_000,
    };
  });
}

/** Deterministic pseudo-random walk. The LCG constants are the widely used
 *  Numerical Recipes parameters; any full-period LCG would do. */
export function walkBars(length: number, seed = 42, start = 100): IndicatorBar[] {
  let state = seed;
  const next = () => {
    state = (state * 1_664_525 + 1_013_904_223) % 4_294_967_296;
    return state / 4_294_967_296;
  };
  const bars: IndicatorBar[] = [];
  let close = start;
  for (let i = 0; i < length; i += 1) {
    const open = close;
    close = Math.max(1, close * (1 + (next() - 0.5) * 0.04));
    const high = Math.max(open, close) * (1 + next() * 0.01);
    const low = Math.min(open, close) * (1 - next() * 0.01);
    bars.push({ t: 1_700_000_000 + i * DAY, o: open, h: high, l: low, c: close, v: Math.round(500_000 + next() * 500_000) });
  }
  return bars;
}

/** A clean sine wave of a known cycle length — the reference signal for the Ehlers
 *  cycle-measurement tests, where "does it find the period we put in" is the only
 *  check that is genuinely independent of the implementation. */
export function sineBars(length: number, period: number, amplitude = 10, base = 100): IndicatorBar[] {
  const closes = Array.from({ length }, (_, i) => base + amplitude * Math.sin((2 * Math.PI * i) / period));
  return barsFromCloses(closes);
}

export function zeroVolume(bars: IndicatorBar[]): IndicatorBar[] {
  return bars.map((bar) => ({ ...bar, v: 0 }));
}
