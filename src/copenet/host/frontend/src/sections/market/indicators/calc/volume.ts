// Volume-flow indicators.
//
// Every function here returns an all-null series when the bars carry no volume. That is the
// one behaviour worth stating twice: a volume indicator computed from zeros is not zero, it
// is unknown, and drawing a flat line for it invents a measurement. `market.ticker` does
// return v: 0 for instruments with no reported volume, so this path is live, not theoretical.

import { clamp, emptySeries, finite, hasVolume, rollingSum, safeDiv } from '../math';
import type { IndicatorBar, IndicatorSeries } from '../types';

/** On-Balance Volume (Joe Granville, 1963): a running total that adds the bar's whole volume
 *  on an up close and subtracts it on a down close. Only the SHAPE is meaningful — the level
 *  depends entirely on where the series happens to start, so it begins at zero on the first
 *  bar of the loaded history and is not comparable across symbols. */
export function onBalanceVolume(bars: IndicatorBar[]): IndicatorSeries {
  if (!hasVolume(bars)) return emptySeries(bars.length);
  const out = emptySeries(bars.length);
  let total = 0;
  for (let i = 0; i < bars.length; i += 1) {
    const volume = Number.isFinite(bars[i].v) ? Math.max(0, bars[i].v) : 0;
    if (i > 0) {
      if (bars[i].c > bars[i - 1].c) total += volume;
      else if (bars[i].c < bars[i - 1].c) total -= volume;
    }
    out[i] = total;
  }
  return out;
}

/** Chaikin Money Flow (Marc Chaikin): volume weighted by where each bar closed within its own
 *  range, summed over n bars and divided by total volume.
 *
 *  A bar whose high equals its low has an undefined location multiplier; it contributes zero
 *  money flow rather than being skipped, so the denominator still counts its volume. That is
 *  Chaikin's treatment and it keeps the ratio bounded to +/-1. */
export function chaikinMoneyFlow(bars: IndicatorBar[], period: number): IndicatorSeries {
  if (!hasVolume(bars)) return emptySeries(bars.length);
  const moneyFlowVolume: IndicatorSeries = bars.map((bar) => {
    const volume = Number.isFinite(bar.v) ? Math.max(0, bar.v) : 0;
    const span = bar.h - bar.l;
    if (span === 0) return 0;
    const multiplier = ((bar.c - bar.l) - (bar.h - bar.c)) / span;
    return finite(multiplier * volume) ?? 0;
  });
  const volumes: IndicatorSeries = bars.map((bar) => (Number.isFinite(bar.v) ? Math.max(0, bar.v) : 0));
  const flowSum = rollingSum(moneyFlowVolume, period);
  const volumeSum = rollingSum(volumes, period);
  return flowSum.map((value, i) => {
    const ratio = safeDiv(finite(value), finite(volumeSum[i]));
    return ratio == null ? null : clamp(ratio, -1, 1);
  });
}
