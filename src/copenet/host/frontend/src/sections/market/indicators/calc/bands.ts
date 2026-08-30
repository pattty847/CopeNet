// Channels, envelopes and the trailing-stop overlay. All draw on the price scale.

import { atr, emptySeries, ema, finite, highest, lowest, sma, sourceValues, stdev } from '../math';
import type { IndicatorBar, IndicatorSeries, IndicatorSource } from '../types';

/** Declared as a type alias rather than an interface on purpose: only an alias picks up an
 *  implicit index signature, which is what lets a named result be handed straight to the
 *  registry's `Record<string, IndicatorSeries>` without a spread at every call site. */
export type BandResult = {
  upper: IndicatorSeries;
  middle: IndicatorSeries;
  lower: IndicatorSeries;
};

/** Bollinger Bands (John Bollinger). Midline is an SMA; the edges are k POPULATION standard
 *  deviations away. Population rather than sample is Bollinger's own definition — using the
 *  n-1 sample deviation widens every band slightly and is a common silent divergence. */
export function bollingerBands(
  bars: IndicatorBar[],
  period: number,
  multiplier: number,
  source: IndicatorSource,
): BandResult {
  const values = sourceValues(bars, source);
  const middle = sma(values, period);
  const deviation = stdev(values, period);
  const upper = emptySeries(bars.length);
  const lower = emptySeries(bars.length);
  for (let i = 0; i < bars.length; i += 1) {
    const mid = finite(middle[i]);
    const dev = finite(deviation[i]);
    if (mid == null || dev == null) continue;
    upper[i] = mid + multiplier * dev;
    lower[i] = mid - multiplier * dev;
  }
  return { upper, middle, lower };
}

/** Keltner Channels, in the modern ATR formulation (Linda Raschke's revision of Chester
 *  Keltner's original): an EMA midline with edges set by a multiple of Average True Range.
 *  The original 1960 version used a simple MA of typical price and a moving average of the
 *  high-low range; the ATR form is what "Keltner Channel" means in current usage, and the
 *  registry says so in its description. */
export function keltnerChannels(
  bars: IndicatorBar[],
  period: number,
  atrPeriod: number,
  multiplier: number,
  source: IndicatorSource,
): BandResult {
  const middle = ema(sourceValues(bars, source), period);
  const range = atr(bars, atrPeriod);
  const upper = emptySeries(bars.length);
  const lower = emptySeries(bars.length);
  for (let i = 0; i < bars.length; i += 1) {
    const mid = finite(middle[i]);
    const width = finite(range[i]);
    if (mid == null || width == null) continue;
    upper[i] = mid + multiplier * width;
    lower[i] = mid - multiplier * width;
  }
  return { upper, middle, lower };
}

/** Donchian Channels (Richard Donchian): the highest high and lowest low of the last n bars.
 *
 *  The CURRENT bar is included, which is the standard definition and means price can touch
 *  but never exceed the channel. The breakout-system variant excludes the current bar so that
 *  a break is detectable on the bar it happens; that is a different indicator and is not what
 *  this draws. */
export function donchianChannels(bars: IndicatorBar[], period: number): BandResult {
  const upper = highest(bars.map((bar) => bar.h), period);
  const lower = lowest(bars.map((bar) => bar.l), period);
  const middle = upper.map((value, i) => {
    const high = finite(value);
    const low = finite(lower[i]);
    return high == null || low == null ? null : (high + low) / 2;
  });
  return { upper, middle, lower };
}

export type SupertrendResult = {
  line: IndicatorSeries;
  /** +1 while the stop trails below price, -1 while it trails above. Drives the line colour. */
  direction: IndicatorSeries;
};

/** Supertrend: an ATR trailing stop that flips side when price closes through it.
 *
 *  The two "final band" recursions are the whole indicator. A band only ratchets in the
 *  direction that tightens the stop — the upper band may fall but never rise while the trend
 *  holds — and it resets only when the prior close breaks through. Dropping that recursion
 *  and plotting the raw bands is a common and visibly wrong simplification: the line then
 *  whipsaws on every bar instead of trailing. */
export function supertrend(bars: IndicatorBar[], atrPeriod: number, multiplier: number): SupertrendResult {
  const line = emptySeries(bars.length);
  const direction = emptySeries(bars.length);
  const range = atr(bars, atrPeriod);
  let finalUpper: number | null = null;
  let finalLower: number | null = null;
  let trend = 1;
  for (let i = 0; i < bars.length; i += 1) {
    const width = finite(range[i]);
    if (width == null) continue;
    const mid = (bars[i].h + bars[i].l) / 2;
    const basicUpper = mid + multiplier * width;
    const basicLower = mid - multiplier * width;
    const previousClose = i > 0 ? bars[i - 1].c : bars[i].c;

    finalUpper = finalUpper == null || basicUpper < finalUpper || previousClose > finalUpper
      ? basicUpper
      : finalUpper;
    finalLower = finalLower == null || basicLower > finalLower || previousClose < finalLower
      ? basicLower
      : finalLower;

    if (trend === 1 && bars[i].c < finalLower) trend = -1;
    else if (trend === -1 && bars[i].c > finalUpper) trend = 1;

    line[i] = trend === 1 ? finalLower : finalUpper;
    direction[i] = trend;
  }
  return { line, direction };
}
