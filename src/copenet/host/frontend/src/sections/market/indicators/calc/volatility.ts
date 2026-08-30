// Volatility and range. These measure how far price moves, never which way.

import { atr, emptySeries, finite, sma, stdev } from '../math';
import type { IndicatorBar, IndicatorContext, IndicatorSeries } from '../types';

/** Average True Range (Wilder). True range already accounts for gaps, which is the whole
 *  reason it exists — a plain high-minus-low average understates every gapping instrument. */
export function averageTrueRange(bars: IndicatorBar[], period: number): IndicatorSeries {
  return atr(bars, period);
}

/** Average range as a percentage — the "ADR%" screening figure.
 *
 *  Computed as the mean of (high / low - 1) over n bars, which is the form used for
 *  position sizing because it is scale-free and comparable across instruments. Deliberately
 *  NOT true-range-based: this measures the typical intra-bar excursion, so including gaps
 *  would be measuring something else.
 *
 *  Named "Average Range %" rather than "Average DAILY Range" because this chart also serves
 *  weekly and monthly bars, where the daily reading of the number would be wrong. */
export function averageRangePercent(bars: IndicatorBar[], period: number): IndicatorSeries {
  const ratios: IndicatorSeries = bars.map((bar) => {
    if (!(bar.l > 0) || !Number.isFinite(bar.h)) return null;
    return finite(100 * (bar.h / bar.l - 1));
  });
  return sma(ratios, period);
}

/** Historical (close-to-close) volatility, annualised, in percent.
 *
 *  Standard deviation of LOG returns — log rather than simple returns so that the measure is
 *  symmetric and additive over time, which is what makes the sqrt-of-time annualisation
 *  valid at all.
 *
 *  Annualisation follows the CHART's own interval by default: 252 bars a year on daily, 52 on
 *  weekly, 12 on monthly. Hardcoding 252 is the usual shortcut and it overstates a monthly
 *  chart's volatility by roughly 4.6x. The operator can still pin a basis explicitly. */
export function historicalVolatility(
  bars: IndicatorBar[],
  period: number,
  basis: string,
  context: IndicatorContext,
): IndicatorSeries {
  const returns = emptySeries(bars.length);
  for (let i = 1; i < bars.length; i += 1) {
    const previous = bars[i - 1].c;
    const current = bars[i].c;
    if (!(previous > 0) || !(current > 0)) continue;
    returns[i] = finite(Math.log(current / previous));
  }
  const deviation = stdev(returns, period);
  const perYear = basis === 'auto' ? context.barsPerYear : Number(basis);
  const scale = Number.isFinite(perYear) && perYear > 0 ? Math.sqrt(perYear) : 1;
  return deviation.map((value) => {
    const usable = finite(value);
    return usable == null ? null : usable * scale * 100;
  });
}
