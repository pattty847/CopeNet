// Moving averages and the price-anchored overlays built directly on them.
//
// Formula provenance is documented per function. Nothing here is transcribed from a vendor
// script; each is the published definition, implemented from the definition.

import {
  emptySeries,
  ema,
  finite,
  hasVolume,
  sourceValues,
  typicalPrice,
  wma,
  sma,
} from '../math';
import type { IndicatorBar, IndicatorSeries, IndicatorSource } from '../types';

export function simpleMovingAverage(bars: IndicatorBar[], period: number, source: IndicatorSource): IndicatorSeries {
  return sma(sourceValues(bars, source), period);
}

export function exponentialMovingAverage(bars: IndicatorBar[], period: number, source: IndicatorSource): IndicatorSeries {
  return ema(sourceValues(bars, source), period);
}

export function weightedMovingAverage(bars: IndicatorBar[], period: number, source: IndicatorSource): IndicatorSeries {
  return wma(sourceValues(bars, source), period);
}

/** Hull Moving Average (Alan Hull, 2005).
 *
 *  HMA(n) = WMA( 2*WMA(n/2) - WMA(n), sqrt(n) )
 *
 *  The doubled half-length WMA minus the full-length WMA is a deliberate overshoot that
 *  cancels the lag; the sqrt(n) smoothing then removes the noise that overshoot introduces.
 *  Half-length and sqrt-length are rounded, which is what makes HMA(9) a well-defined series
 *  rather than an interpolation question. */
export function hullMovingAverage(bars: IndicatorBar[], period: number, source: IndicatorSource): IndicatorSeries {
  const values = sourceValues(bars, source);
  const half = Math.max(1, Math.round(period / 2));
  const root = Math.max(1, Math.round(Math.sqrt(period)));
  const fast = wma(values, half);
  const slow = wma(values, period);
  const raw: IndicatorSeries = fast.map((value, i) => {
    const a = finite(value);
    const b = finite(slow[i]);
    return a == null || b == null ? null : 2 * a - b;
  });
  return wma(raw, root);
}

/** Rolling VWAP over the last `period` bars: sum(typical price x volume) / sum(volume).
 *
 *  Honest naming matters here. A true VWAP is anchored to a SESSION and accumulates
 *  intraday. This chart's finest granularity is one daily bar, so a session VWAP would be
 *  identical to the day's own typical price and would tell you nothing. What is meaningful
 *  on daily/weekly/monthly bars is a rolling volume-weighted average, and that is what this
 *  computes — the registry labels it "Rolling VWAP" with its bar count, never bare "VWAP".
 *
 *  Returns null wherever the window carries no volume, rather than falling back to an
 *  unweighted average that would silently stop being volume-weighted. */
export function rollingVwap(bars: IndicatorBar[], period: number): IndicatorSeries {
  const out = emptySeries(bars.length);
  if (!hasVolume(bars)) return out;
  const prices = typicalPrice(bars);
  let priceVolume = 0;
  let volume = 0;
  for (let i = 0; i < bars.length; i += 1) {
    const enteringVolume = Number.isFinite(bars[i].v) ? Math.max(0, bars[i].v) : 0;
    priceVolume += prices[i] * enteringVolume;
    volume += enteringVolume;
    if (i >= period) {
      const leavingVolume = Number.isFinite(bars[i - period].v) ? Math.max(0, bars[i - period].v) : 0;
      priceVolume -= prices[i - period] * leavingVolume;
      volume -= leavingVolume;
    }
    if (i >= period - 1 && volume > 0) out[i] = priceVolume / volume;
  }
  return out;
}
