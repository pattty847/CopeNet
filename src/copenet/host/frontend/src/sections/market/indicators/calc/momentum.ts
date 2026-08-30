// Momentum and oscillator families. All render in their own pane.
//
// Two conventions used consistently across this file, both chosen so a chart never shows a
// number that is not a measurement:
//
//   * A ZERO RANGE means "no information", not "extreme". A window whose high equals its low
//     produces null for Stochastic and Williams %R rather than 0 or 100.
//   * A FLAT series — no gains and no losses at all — produces the NEUTRAL midpoint for the
//     ratio oscillators (RSI 50, MFI 50). The textbook 100 - 100/(1+0/0) is undefined; the
//     usual library behaviour of reporting 100 renders a dead-flat series as maximally
//     overbought, which is the least defensible of the available answers.

import {
  clamp,
  emptySeries,
  ema,
  finite,
  hasVolume,
  highest,
  lowest,
  rma,
  rollingSum,
  safeDiv,
  sma,
  sourceValues,
  trueRange,
  typicalPrice,
} from '../math';
import type { IndicatorBar, IndicatorSeries, IndicatorSource } from '../types';

/** Relative Strength Index (J. Welles Wilder, 1978), Wilder-smoothed. */
export function relativeStrengthIndex(bars: IndicatorBar[], period: number, source: IndicatorSource): IndicatorSeries {
  const values = sourceValues(bars, source);
  const gains = emptySeries(values.length);
  const losses = emptySeries(values.length);
  for (let i = 1; i < values.length; i += 1) {
    const change = values[i] - values[i - 1];
    gains[i] = Math.max(change, 0);
    losses[i] = Math.max(-change, 0);
  }
  const averageGain = rma(gains, period);
  const averageLoss = rma(losses, period);
  const out = emptySeries(values.length);
  for (let i = 0; i < values.length; i += 1) {
    const gain = finite(averageGain[i]);
    const loss = finite(averageLoss[i]);
    if (gain == null || loss == null) continue;
    if (gain === 0 && loss === 0) { out[i] = 50; continue; }
    if (loss === 0) { out[i] = 100; continue; }
    out[i] = 100 - 100 / (1 + gain / loss);
  }
  return out;
}

/** Raw %K: where the close sits inside the last n bars' high-low range, as a percentage. */
function rawStochastic(values: IndicatorSeries, highs: IndicatorSeries, lows: IndicatorSeries, period: number): IndicatorSeries {
  const top = highest(highs, period);
  const bottom = lowest(lows, period);
  const out = emptySeries(values.length);
  for (let i = 0; i < values.length; i += 1) {
    const value = finite(values[i]);
    const high = finite(top[i]);
    const low = finite(bottom[i]);
    if (value == null || high == null || low == null) continue;
    const span = high - low;
    if (span === 0) continue; // a flat window locates nothing
    out[i] = clamp((100 * (value - low)) / span, 0, 100);
  }
  return out;
}

export type StochasticResult = { k: IndicatorSeries; d: IndicatorSeries };

/** Pin a 0-100 series to its own declared bounds. See `clamp` in math.ts for why. */
function boundedPercent(series: IndicatorSeries): IndicatorSeries {
  return series.map((value) => (value == null ? null : clamp(value, 0, 100)));
}

/** Stochastic Oscillator (George Lane). `smooth` of 1 is the fast stochastic; 3 is the
 *  conventional slow stochastic, which is the default. */
export function stochastic(bars: IndicatorBar[], period: number, smooth: number, signal: number): StochasticResult {
  const raw = rawStochastic(
    bars.map((bar) => bar.c),
    bars.map((bar) => bar.h),
    bars.map((bar) => bar.l),
    period,
  );
  // Smoothing an already-bounded series keeps it bounded, but the division that produced it
  // does not land exactly on 100, so re-pin both outputs to the range the pane declares.
  const k = boundedPercent(smooth <= 1 ? raw : sma(raw, smooth));
  return { k, d: boundedPercent(sma(k, signal)) };
}

/** Stochastic RSI (Chande & Kroll): the stochastic formula applied to RSI rather than price,
 *  which is why it saturates far more often than either input. Scaled 0-100 to match the
 *  Stochastic's pane, not 0-1. */
export function stochasticRsi(
  bars: IndicatorBar[],
  rsiPeriod: number,
  stochPeriod: number,
  smooth: number,
  signal: number,
  source: IndicatorSource,
): StochasticResult {
  const rsi = relativeStrengthIndex(bars, rsiPeriod, source);
  const raw = rawStochastic(rsi, rsi, rsi, stochPeriod);
  const k = boundedPercent(smooth <= 1 ? raw : sma(raw, smooth));
  return { k, d: boundedPercent(sma(k, signal)) };
}

export type MacdResult = { macd: IndicatorSeries; signal: IndicatorSeries; histogram: IndicatorSeries };

/** Moving Average Convergence/Divergence (Gerald Appel). The signal line is an EMA OF THE
 *  MACD LINE, so it inherits the slow EMA's warm-up on top of its own — the histogram is
 *  legitimately null for roughly slow + signal bars, not just slow. */
export function macd(
  bars: IndicatorBar[],
  fastPeriod: number,
  slowPeriod: number,
  signalPeriod: number,
  source: IndicatorSource,
): MacdResult {
  const values = sourceValues(bars, source);
  const fast = ema(values, fastPeriod);
  const slow = ema(values, slowPeriod);
  const line = emptySeries(values.length);
  for (let i = 0; i < values.length; i += 1) {
    const a = finite(fast[i]);
    const b = finite(slow[i]);
    if (a == null || b == null) continue;
    line[i] = a - b;
  }
  const signal = ema(line, signalPeriod);
  const histogram = line.map((value, i) => {
    const a = finite(value);
    const b = finite(signal[i]);
    return a == null || b == null ? null : a - b;
  });
  return { macd: line, signal, histogram };
}

/** Rate of Change / Momentum. `percent` is ROC; `difference` is raw momentum in price units. */
export function rateOfChange(
  bars: IndicatorBar[],
  period: number,
  mode: 'percent' | 'difference',
  source: IndicatorSource,
): IndicatorSeries {
  const values = sourceValues(bars, source);
  const out = emptySeries(values.length);
  for (let i = period; i < values.length; i += 1) {
    const past = values[i - period];
    if (mode === 'difference') { out[i] = finite(values[i] - past); continue; }
    out[i] = safeDiv(100 * (values[i] - past), past);
  }
  return out;
}

/** Commodity Channel Index (Donald Lambert, 1980). The 0.015 constant is Lambert's own
 *  scaling choice — it places roughly 70-80% of readings inside +/-100 and has no derivation.
 *  Uses MEAN ABSOLUTE deviation, not standard deviation; substituting stdev is a frequent
 *  and silent error that changes the scale. */
export function commodityChannelIndex(bars: IndicatorBar[], period: number): IndicatorSeries {
  const prices = typicalPrice(bars);
  const means = sma(prices, period);
  const out = emptySeries(bars.length);
  for (let i = period - 1; i < bars.length; i += 1) {
    const mean = finite(means[i]);
    if (mean == null) continue;
    let deviation = 0;
    for (let k = i - period + 1; k <= i; k += 1) deviation += Math.abs(prices[k] - mean);
    deviation /= period;
    if (deviation === 0) continue; // flat window: the index is undefined, not zero
    out[i] = (prices[i] - mean) / (0.015 * deviation);
  }
  return out;
}

/** Williams %R (Larry Williams). Same geometry as the raw stochastic, reported as 0 to -100
 *  from the top of the range instead of 0 to 100 from the bottom. */
export function williamsR(bars: IndicatorBar[], period: number): IndicatorSeries {
  const top = highest(bars.map((bar) => bar.h), period);
  const bottom = lowest(bars.map((bar) => bar.l), period);
  const out = emptySeries(bars.length);
  for (let i = 0; i < bars.length; i += 1) {
    const high = finite(top[i]);
    const low = finite(bottom[i]);
    if (high == null || low == null) continue;
    const span = high - low;
    if (span === 0) continue;
    out[i] = clamp((-100 * (high - bars[i].c)) / span, -100, 0);
  }
  return out;
}

export type AdxResult = { adx: IndicatorSeries; plusDi: IndicatorSeries; minusDi: IndicatorSeries };

/** Average Directional Index with the +DI/-DI pair (Wilder, 1978).
 *
 *  Directional movement is EXCLUSIVE: a bar contributes to +DM or -DM or neither, never
 *  both, and an inside bar contributes nothing. Both are Wilder-smoothed over `period`
 *  before the ratio, and ADX is a second Wilder smoothing of DX over `adxPeriod`, which is
 *  why ADX needs roughly period + adxPeriod bars before it says anything. */
export function averageDirectionalIndex(bars: IndicatorBar[], period: number, adxPeriod: number): AdxResult {
  const plusDm = emptySeries(bars.length);
  const minusDm = emptySeries(bars.length);
  for (let i = 1; i < bars.length; i += 1) {
    const upMove = bars[i].h - bars[i - 1].h;
    const downMove = bars[i - 1].l - bars[i].l;
    plusDm[i] = upMove > downMove && upMove > 0 ? upMove : 0;
    minusDm[i] = downMove > upMove && downMove > 0 ? downMove : 0;
  }
  const range = trueRange(bars);
  // Bar 0 has no directional movement, so drop its true range too — otherwise the smoothed
  // TR is seeded one bar earlier than the smoothed DM and every DI is biased low at the start.
  const alignedRange: IndicatorSeries = range.map((value, i) => (i === 0 ? null : value));
  const smoothedRange = rma(alignedRange, period);
  const smoothedPlus = rma(plusDm, period);
  const smoothedMinus = rma(minusDm, period);

  const plusDi = emptySeries(bars.length);
  const minusDi = emptySeries(bars.length);
  const dx = emptySeries(bars.length);
  for (let i = 0; i < bars.length; i += 1) {
    const tr = finite(smoothedRange[i]);
    const up = finite(smoothedPlus[i]);
    const down = finite(smoothedMinus[i]);
    if (tr == null || up == null || down == null || tr === 0) continue;
    const positive = (100 * up) / tr;
    const negative = (100 * down) / tr;
    plusDi[i] = positive;
    minusDi[i] = negative;
    const total = positive + negative;
    dx[i] = total === 0 ? 0 : (100 * Math.abs(positive - negative)) / total;
  }
  return { adx: rma(dx, adxPeriod), plusDi, minusDi };
}

/** Money Flow Index — RSI computed on typical price times volume rather than on price alone.
 *
 *  Requires real volume. When the series carries none, every value is null: an MFI drawn from
 *  zero volume is a flat 50 line that looks exactly like a genuine neutral reading. */
export function moneyFlowIndex(bars: IndicatorBar[], period: number): IndicatorSeries {
  if (!hasVolume(bars)) return emptySeries(bars.length);
  const prices = typicalPrice(bars);
  const positive = emptySeries(bars.length);
  const negative = emptySeries(bars.length);
  for (let i = 1; i < bars.length; i += 1) {
    const flow = prices[i] * (Number.isFinite(bars[i].v) ? Math.max(0, bars[i].v) : 0);
    positive[i] = prices[i] > prices[i - 1] ? flow : 0;
    negative[i] = prices[i] < prices[i - 1] ? flow : 0;
  }
  const positiveFlow = rollingSum(positive, period);
  const negativeFlow = rollingSum(negative, period);
  const out = emptySeries(bars.length);
  for (let i = 0; i < bars.length; i += 1) {
    const up = finite(positiveFlow[i]);
    const down = finite(negativeFlow[i]);
    if (up == null || down == null) continue;
    if (up === 0 && down === 0) { out[i] = 50; continue; }
    if (down === 0) { out[i] = 100; continue; }
    out[i] = 100 - 100 / (1 + up / down);
  }
  return out;
}
