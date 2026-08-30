// Numeric primitives shared by every calculation family.
//
// Two rules hold everywhere in this file and everything built on it:
//
//   1. `null` is the only way to say "no value here". NaN and Infinity never leave a
//      primitive — a zero denominator, an empty window or a warm-up gap all return null, so
//      a downstream consumer never has to guess whether a number is real.
//   2. Every function is CAUSAL. Index i is computed from indices <= i and nothing else.
//      That is what makes "compute over full history, then slice to the visible range"
//      identical to "compute over the visible range" for every bar the two share, and it is
//      the property the look-ahead tests assert across the whole registry.

import type { IndicatorBar, IndicatorSeries, IndicatorSource } from './types';

/** Anything non-finite becomes null at the boundary rather than propagating. */
export function finite(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Division that reports an unusable denominator instead of returning Infinity or NaN. */
export function safeDiv(numerator: number | null, denominator: number | null): number | null {
  if (numerator == null || denominator == null) return null;
  if (denominator === 0) return null;
  return finite(numerator / denominator);
}

export function sourceValues(bars: IndicatorBar[], source: IndicatorSource): number[] {
  switch (source) {
    case 'open': return bars.map((bar) => bar.o);
    case 'high': return bars.map((bar) => bar.h);
    case 'low': return bars.map((bar) => bar.l);
    case 'hl2': return bars.map((bar) => (bar.h + bar.l) / 2);
    case 'hlc3': return bars.map((bar) => (bar.h + bar.l + bar.c) / 3);
    case 'ohlc4': return bars.map((bar) => (bar.o + bar.h + bar.l + bar.c) / 4);
    case 'close':
    default: return bars.map((bar) => bar.c);
  }
}

export function typicalPrice(bars: IndicatorBar[]): number[] {
  return bars.map((bar) => (bar.h + bar.l + bar.c) / 3);
}

/** An all-null series the length of the input. The honest answer for "not enough history". */
export function emptySeries(length: number): IndicatorSeries {
  return new Array<number | null>(length).fill(null);
}

/** Simple moving average. A window containing a null produces a null — a partial window is
 *  not a smaller average, it is a different statistic. */
export function sma(values: IndicatorSeries, period: number): IndicatorSeries {
  const out = emptySeries(values.length);
  if (period < 1) return out;
  // Summed directly over the window rather than by adding the entering bar and subtracting
  // the leaving one. The sliding form is O(n) instead of O(n*period), but it carries
  // accumulated rounding forward for the whole series — enough to push a mathematically
  // bounded oscillator a few ulps outside its own range, which then defeats the pane's
  // declared scale. Windows here are tens of bars, so the direct form costs nothing
  // measurable and is exactly right.
  for (let i = period - 1; i < values.length; i += 1) {
    let sum = 0;
    let usable = true;
    for (let k = i - period + 1; k <= i; k += 1) {
      const value = finite(values[k]);
      if (value == null) { usable = false; break; }
      sum += value;
    }
    if (usable) out[i] = sum / period;
  }
  return out;
}

/** Exponential moving average, seeded with the SMA of the first full window.
 *
 *  Seeding matters more than it looks: seeding from the first value instead makes early
 *  output depend on one arbitrary bar and takes several multiples of the period to decay,
 *  which shows up as a visibly wrong EMA at the left edge of a short chart. */
export function ema(values: IndicatorSeries, period: number): IndicatorSeries {
  const out = emptySeries(values.length);
  if (period < 1) return out;
  const alpha = 2 / (period + 1);
  let previous: number | null = null;
  let sum = 0;
  let seeded = 0;
  for (let i = 0; i < values.length; i += 1) {
    const value = finite(values[i]);
    // An interior null reports null rather than repeating the last value — a held-over
    // number is indistinguishable from a real one on a chart.
    if (value == null) { out[i] = null; continue; }
    if (previous == null) {
      sum += value;
      seeded += 1;
      if (seeded === period) { previous = sum / period; out[i] = previous; }
      continue;
    }
    previous = value * alpha + previous * (1 - alpha);
    out[i] = previous;
  }
  return out;
}

/** Wilder's smoothing (RMA): the 1/period recursion behind RSI, ATR, ADX and MFI.
 *  Distinct from EMA(period) — Wilder's alpha is 1/n, not 2/(n+1). */
export function rma(values: IndicatorSeries, period: number): IndicatorSeries {
  const out = emptySeries(values.length);
  if (period < 1) return out;
  let previous: number | null = null;
  let sum = 0;
  let seeded = 0;
  for (let i = 0; i < values.length; i += 1) {
    const value = finite(values[i]);
    if (value == null) { out[i] = null; continue; }
    if (previous == null) {
      sum += value;
      seeded += 1;
      if (seeded === period) { previous = sum / period; out[i] = previous; }
      continue;
    }
    previous = (previous * (period - 1) + value) / period;
    out[i] = previous;
  }
  return out;
}

/** Linearly weighted moving average: weight i+1 on the i-th oldest bar in the window. */
export function wma(values: IndicatorSeries, period: number): IndicatorSeries {
  const out = emptySeries(values.length);
  if (period < 1) return out;
  const denominator = (period * (period + 1)) / 2;
  for (let i = period - 1; i < values.length; i += 1) {
    let weighted = 0;
    let usable = true;
    for (let k = 0; k < period; k += 1) {
      const value = finite(values[i - period + 1 + k]);
      if (value == null) { usable = false; break; }
      weighted += value * (k + 1);
    }
    if (usable) out[i] = weighted / denominator;
  }
  return out;
}

/** Population standard deviation over a rolling window — the deviation Bollinger uses.
 *  Computed from the window directly rather than from running sums of squares, which loses
 *  precision badly on large price levels. */
export function stdev(values: IndicatorSeries, period: number): IndicatorSeries {
  const out = emptySeries(values.length);
  if (period < 1) return out;
  const means = sma(values, period);
  for (let i = period - 1; i < values.length; i += 1) {
    const mean = means[i];
    if (mean == null) continue;
    let total = 0;
    let usable = true;
    for (let k = i - period + 1; k <= i; k += 1) {
      const value = finite(values[k]);
      if (value == null) { usable = false; break; }
      total += (value - mean) ** 2;
    }
    if (usable) out[i] = Math.sqrt(total / period);
  }
  return out;
}

export function highest(values: IndicatorSeries, period: number): IndicatorSeries {
  const out = emptySeries(values.length);
  for (let i = period - 1; i < values.length; i += 1) {
    let best: number | null = null;
    let usable = true;
    for (let k = i - period + 1; k <= i; k += 1) {
      const value = finite(values[k]);
      if (value == null) { usable = false; break; }
      if (best == null || value > best) best = value;
    }
    if (usable) out[i] = best;
  }
  return out;
}

export function lowest(values: IndicatorSeries, period: number): IndicatorSeries {
  const out = emptySeries(values.length);
  for (let i = period - 1; i < values.length; i += 1) {
    let best: number | null = null;
    let usable = true;
    for (let k = i - period + 1; k <= i; k += 1) {
      const value = finite(values[k]);
      if (value == null) { usable = false; break; }
      if (best == null || value < best) best = value;
    }
    if (usable) out[i] = best;
  }
  return out;
}

/** Rolling sum. Null inside the window makes the whole window null, matching `sma`. */
export function rollingSum(values: IndicatorSeries, period: number): IndicatorSeries {
  const averages = sma(values, period);
  return averages.map((value) => (value == null ? null : value * period));
}

/** Wilder's true range. Bar 0 has no previous close, so it falls back to the bar's own
 *  range rather than being dropped — the standard treatment. */
export function trueRange(bars: IndicatorBar[]): IndicatorSeries {
  return bars.map((bar, i) => {
    if (i === 0) return finite(bar.h - bar.l);
    const previousClose = bars[i - 1].c;
    return finite(Math.max(bar.h - bar.l, Math.abs(bar.h - previousClose), Math.abs(bar.l - previousClose)));
  });
}

/** Average true range with Wilder smoothing — the ATR every channel and stop uses. */
export function atr(bars: IndicatorBar[], period: number): IndicatorSeries {
  return rma(trueRange(bars), period);
}

/** Element-wise subtraction that keeps null semantics. */
export function subtract(left: IndicatorSeries, right: IndicatorSeries): IndicatorSeries {
  return left.map((value, i) => {
    const a = finite(value);
    const b = finite(right[i]);
    return a == null || b == null ? null : a - b;
  });
}

export function mapSeries(values: IndicatorSeries, fn: (value: number, index: number) => number | null): IndicatorSeries {
  return values.map((value, i) => {
    const usable = finite(value);
    return usable == null ? null : finite(fn(usable, i));
  });
}

/** Pin a value to a bound the formula already guarantees.
 *
 *  Not defensive rounding: Stochastic, Williams %R and CMF are bounded by construction, but
 *  `100 * (close - low) / (high - low)` with close === high evaluates to 100.00000000000001
 *  in binary floating point. That excess is invisible on a chart and still wrong — it makes a
 *  bounded oscillator fall outside the `paneRange` it declares, which the pane then has to
 *  autoscale around. Clamp where the bound is a mathematical property, never to hide one. */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Does this series carry any volume at all? Volume indicators must say "unavailable"
 *  rather than draw a flat zero line, which reads as a real measurement of nothing. */
export function hasVolume(bars: IndicatorBar[]): boolean {
  return bars.some((bar) => Number.isFinite(bar.v) && bar.v > 0);
}
