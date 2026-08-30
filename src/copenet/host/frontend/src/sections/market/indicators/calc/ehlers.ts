// John Ehlers' digital-signal-processing indicators.
//
// Provenance: these follow the formulations Ehlers published in "Rocket Science for Traders"
// (2001) and "Cybernetic Analysis for Stocks and Futures" (2004), implemented from the
// stated recursions rather than transcribed from any vendor script.
//
// Two implementation notes that matter for correctness:
//
//   * Ehlers writes his phase arithmetic in DEGREES, because his platform's ArcTangent
//     returns degrees. JavaScript's Math.atan returns RADIANS, so MAMA converts explicitly
//     and stays in degrees for every angular step. This is not cosmetic: alpha is
//     fastLimit / deltaPhase, and a delta-phase of 5 degrees is 0.087 radians — feeding
//     radians in makes alpha ~57x too large, pins it to fastLimit on virtually every bar,
//     and turns the adaptive average into a plain fast EMA that still looks entirely
//     plausible on a chart.
//   * These are RECURSIVE filters with long memory. They are still strictly causal, so the
//     look-ahead property holds, but their output near the left edge depends on the seed.
//     Each function nulls its own settling region rather than drawing a filter that has not
//     converged.

import { emptySeries, finite, sourceValues } from '../math';
import type { IndicatorBar, IndicatorSeries, IndicatorSource } from '../types';

/** Ehlers' 2-pole Super Smoother: a Butterworth-response low-pass filter.
 *
 *  c1 + c2 + c3 == 1 by construction, which makes any constant input a fixed point — the
 *  filter passes a flat series through unchanged. That identity is the cheapest correctness
 *  check available on this family and the tests assert it.
 *
 *      a1 = exp(-sqrt(2)*pi / period)
 *      b1 = 2*a1*cos(sqrt(2)*pi / period)
 *      c2 = b1,  c3 = -a1^2,  c1 = 1 - c2 - c3
 *      ss[i] = c1*(src[i] + src[i-1])/2 + c2*ss[i-1] + c3*ss[i-2]
 */
export function superSmoother(bars: IndicatorBar[], period: number, source: IndicatorSource): IndicatorSeries {
  const values = sourceValues(bars, source);
  const out = emptySeries(values.length);
  if (!values.length) return out;
  const angle = (Math.SQRT2 * Math.PI) / Math.max(1, period);
  const a1 = Math.exp(-angle);
  const c2 = 2 * a1 * Math.cos(angle);
  const c3 = -(a1 * a1);
  const c1 = 1 - c2 - c3;
  out[0] = values[0];
  if (values.length > 1) out[1] = values[1];
  for (let i = 2; i < values.length; i += 1) {
    const previous = finite(out[i - 1]) ?? values[i - 1];
    const older = finite(out[i - 2]) ?? values[i - 2];
    out[i] = finite(c1 * ((values[i] + values[i - 1]) / 2) + c2 * previous + c3 * older);
  }
  return out;
}

export type FisherResult = { fisher: IndicatorSeries; trigger: IndicatorSeries };

/** Fisher Transform (Ehlers, 2002).
 *
 *  Price distributions are not Gaussian; the Fisher transform of a value normalised to
 *  (-1, 1) is, which turns turning points into sharp, unambiguous peaks.
 *
 *      value[i]  = 0.66*((price - minLow)/(maxHigh - minLow) - 0.5) + 0.67*value[i-1]
 *      value     clamped to +/-0.999   (the transform diverges at exactly +/-1)
 *      fisher[i] = 0.5*ln((1 + value)/(1 - value)) + 0.5*fisher[i-1]
 *
 *  The 0.999 clamp is Ehlers' own and is load-bearing: without it a series that touches the
 *  window extreme produces an infinite output.
 *
 *  A window with zero range contributes 0 (the midpoint) rather than dividing by zero, so a
 *  flat series decays smoothly toward 0 instead of producing NaN. */
export function fisherTransform(bars: IndicatorBar[], period: number, source: IndicatorSource): FisherResult {
  const prices = sourceValues(bars, source);
  const fisher = emptySeries(prices.length);
  const trigger = emptySeries(prices.length);
  let value = 0;
  let previousFisher = 0;
  for (let i = 0; i < prices.length; i += 1) {
    if (i < period - 1) continue;
    let high = -Infinity;
    let low = Infinity;
    for (let k = i - period + 1; k <= i; k += 1) {
      if (prices[k] > high) high = prices[k];
      if (prices[k] < low) low = prices[k];
    }
    const span = high - low;
    const normalized = span === 0 ? 0 : (prices[i] - low) / span - 0.5;
    value = 0.66 * normalized + 0.67 * value;
    value = Math.min(0.999, Math.max(-0.999, value));
    const current = 0.5 * Math.log((1 + value) / (1 - value)) + 0.5 * previousFisher;
    trigger[i] = i > period - 1 ? previousFisher : null;
    previousFisher = current;
    fisher[i] = finite(current);
  }
  return { fisher, trigger };
}

/** Instantaneous Trendline (Ehlers, "Cybernetic Analysis"): a near-zero-lag trendline from
 *  the alpha formulation of the Hilbert-transform trend extractor.
 *
 *      it[i] = (a - a^2/4)*p[i] + 0.5*a^2*p[i-1] - (a - 0.75*a^2)*p[i-2]
 *              + 2*(1-a)*it[i-1] - (1-a)^2*it[i-2]
 *
 *  Ehlers seeds the first bars with a simple weighted average because the recursion has no
 *  history to run on; the trigger line is 2*it - it[i-2], a two-bar linear extrapolation of
 *  the trendline itself (not of price, and not a forecast — it uses only past values). */
export function instantaneousTrendline(
  bars: IndicatorBar[],
  alpha: number,
  source: IndicatorSource,
): { trend: IndicatorSeries; trigger: IndicatorSeries } {
  const prices = sourceValues(bars, source);
  const trend = emptySeries(prices.length);
  const trigger = emptySeries(prices.length);
  const a = Math.min(0.99, Math.max(0.01, alpha));
  for (let i = 0; i < prices.length; i += 1) {
    if (i < 7) {
      trend[i] = i >= 2 ? (prices[i] + 2 * prices[i - 1] + prices[i - 2]) / 4 : prices[i];
      continue;
    }
    const previous = finite(trend[i - 1]) ?? prices[i - 1];
    const older = finite(trend[i - 2]) ?? prices[i - 2];
    trend[i] = finite(
      (a - (a * a) / 4) * prices[i]
      + 0.5 * a * a * prices[i - 1]
      - (a - 0.75 * a * a) * prices[i - 2]
      + 2 * (1 - a) * previous
      - (1 - a) * (1 - a) * older,
    );
  }
  for (let i = 2; i < prices.length; i += 1) {
    const current = finite(trend[i]);
    const older = finite(trend[i - 2]);
    if (current == null || older == null) continue;
    trigger[i] = 2 * current - older;
  }
  return { trend, trigger };
}

export type MamaResult = { mama: IndicatorSeries; fama: IndicatorSeries; period: IndicatorSeries };

/** MESA Adaptive Moving Average (Ehlers, "Rocket Science for Traders").
 *
 *  MAMA measures the dominant cycle with a Hilbert transform quadrature pair, converts the
 *  rate of PHASE change into an adaptation rate, and uses that as the EMA alpha. Fast when
 *  phase moves quickly (a trend turn), slow when it crawls (a ranging market). FAMA is a
 *  second pass at half alpha, and the MAMA/FAMA crossover is the signal the pair exists for.
 *
 *  The chain, in order: 4-bar weighted smooth -> 6-tap Hilbert detrender -> in-phase and
 *  quadrature components -> homodyne discriminator for the period -> phase, delta-phase,
 *  alpha -> the two averages.
 *
 *  Three constraints from the source that are easy to drop and expensive to lose:
 *    * the detrender/quadrature taps are scaled by (0.075*period[i-1] + 0.54), which
 *      compensates the Hilbert transform's amplitude dependence on the cycle period;
 *    * the measured period is limited to +/-50% bar over bar and clamped to 6..50, without
 *      which one noisy bar detunes the filter for dozens of bars;
 *    * delta-phase has a floor of one degree, which is what stops alpha from exploding.
 *
 *  Output before `warmup` bars is null: the recursions are still settling and Ehlers' own
 *  code does not treat the early values as meaningful. */
export function mesaAdaptiveMovingAverage(
  bars: IndicatorBar[],
  fastLimit: number,
  slowLimit: number,
  warmup: number,
  source: IndicatorSource,
): MamaResult {
  const prices = sourceValues(bars, source);
  const length = prices.length;
  const mama = emptySeries(length);
  const fama = emptySeries(length);
  const periodOut = emptySeries(length);
  if (!length) return { mama, fama, period: periodOut };

  const smooth = new Array<number>(length).fill(0);
  const detrender = new Array<number>(length).fill(0);
  const inPhase = new Array<number>(length).fill(0);
  const quadrature = new Array<number>(length).fill(0);
  const jI = new Array<number>(length).fill(0);
  const jQ = new Array<number>(length).fill(0);
  const i2 = new Array<number>(length).fill(0);
  const q2 = new Array<number>(length).fill(0);
  const re = new Array<number>(length).fill(0);
  const im = new Array<number>(length).fill(0);
  const period = new Array<number>(length).fill(0);
  const smoothPeriod = new Array<number>(length).fill(0);
  const phase = new Array<number>(length).fill(0);

  // The 6-tap Hilbert quadrature filter Ehlers uses throughout.
  const hilbert = (series: number[], i: number, scale: number): number =>
    (0.0962 * series[i] + 0.5769 * series[i - 2] - 0.5769 * series[i - 4] - 0.0962 * series[i - 6]) * scale;

  const DEGREES = 180 / Math.PI;
  /** Ehlers' delta-phase floor, in degrees. Without it alpha diverges as phase flattens. */
  const MIN_DELTA_PHASE = 1;

  let currentMama = prices[0];
  let currentFama = prices[0];

  for (let i = 0; i < length; i += 1) {
    if (i < 6) {
      smooth[i] = prices[i];
      period[i] = 0;
      smoothPeriod[i] = 0;
      continue;
    }
    smooth[i] = (4 * prices[i] + 3 * prices[i - 1] + 2 * prices[i - 2] + prices[i - 3]) / 10;
    const scale = 0.075 * period[i - 1] + 0.54;
    detrender[i] = hilbert(smooth, i, scale);

    quadrature[i] = hilbert(detrender, i, scale);
    inPhase[i] = detrender[i - 3];

    jI[i] = hilbert(inPhase, i, scale);
    jQ[i] = hilbert(quadrature, i, scale);

    // Phasor advanced 90 degrees, then smoothed. The 0.2/0.8 pair is Ehlers' own.
    let rawI2 = inPhase[i] - jQ[i];
    let rawQ2 = quadrature[i] + jI[i];
    rawI2 = 0.2 * rawI2 + 0.8 * i2[i - 1];
    rawQ2 = 0.2 * rawQ2 + 0.8 * q2[i - 1];
    i2[i] = rawI2;
    q2[i] = rawQ2;

    // Homodyne discriminator: multiply the phasor by its own conjugate one bar back.
    let rawRe = i2[i] * i2[i - 1] + q2[i] * q2[i - 1];
    let rawIm = i2[i] * q2[i - 1] - q2[i] * i2[i - 1];
    rawRe = 0.2 * rawRe + 0.8 * re[i - 1];
    rawIm = 0.2 * rawIm + 0.8 * im[i - 1];
    re[i] = rawRe;
    im[i] = rawIm;

    let measured = period[i - 1];
    if (rawIm !== 0 && rawRe !== 0) measured = 360 / (Math.atan(rawIm / rawRe) * DEGREES);
    if (measured > 1.5 * period[i - 1] && period[i - 1] > 0) measured = 1.5 * period[i - 1];
    if (measured < 0.67 * period[i - 1]) measured = 0.67 * period[i - 1];
    measured = Math.min(50, Math.max(6, measured));
    period[i] = 0.2 * measured + 0.8 * period[i - 1];
    smoothPeriod[i] = 0.33 * period[i] + 0.67 * smoothPeriod[i - 1];

    phase[i] = inPhase[i] !== 0 ? Math.atan(quadrature[i] / inPhase[i]) * DEGREES : phase[i - 1];
    let deltaPhase = phase[i - 1] - phase[i];
    if (deltaPhase < MIN_DELTA_PHASE) deltaPhase = MIN_DELTA_PHASE;

    let alpha = fastLimit / deltaPhase;
    if (alpha < slowLimit) alpha = slowLimit;
    if (alpha > fastLimit) alpha = fastLimit;

    currentMama = alpha * prices[i] + (1 - alpha) * currentMama;
    currentFama = 0.5 * alpha * currentMama + (1 - 0.5 * alpha) * currentFama;

    if (i >= warmup) {
      mama[i] = finite(currentMama);
      fama[i] = finite(currentFama);
      periodOut[i] = finite(smoothPeriod[i]);
    }
  }
  return { mama, fama, period: periodOut };
}
