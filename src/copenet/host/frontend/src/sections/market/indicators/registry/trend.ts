// Trend overlays. All draw on the price pane and share the candle scale.

import {
  bollingerBands,
  donchianChannels,
  keltnerChannels,
  supertrend,
} from '../calc/bands';
import {
  exponentialMovingAverage,
  hullMovingAverage,
  rollingVwap,
  simpleMovingAverage,
  weightedMovingAverage,
} from '../calc/movingAverages';
import { readNumber, readPeriod, readSource } from '../config';
import { BAND_EDGE, BAND_MID, SERIES_COLORS } from '../palette';
import type { IndicatorDefinition, IndicatorInput } from '../types';

const SOURCE_INPUT: IndicatorInput = { kind: 'source', key: 'source', label: 'Source', default: 'close', advanced: true };

function periodInput(fallback: number, max = 400): IndicatorInput {
  return { kind: 'number', key: 'period', label: 'Length', default: fallback, min: 1, max, step: 1 };
}

/** The four plain averages differ only in their kernel, so they are generated rather than
 *  written out four times — the shape is genuinely identical and duplicating it invites the
 *  four copies to drift. */
function movingAverage(
  id: string,
  name: string,
  defaultPeriod: number,
  color: string,
  compute: (bars: Parameters<typeof simpleMovingAverage>[0], period: number, source: ReturnType<typeof readSource>) => ReturnType<typeof simpleMovingAverage>,
  description?: string,
  /** Bars needed before every output exists, when that is not simply the length. */
  warmupFor: (period: number) => number = (period) => period,
): IndicatorDefinition {
  return {
    id,
    name,
    category: 'trend',
    description,
    placement: 'price',
    requires: ['close'],
    inputs: [periodInput(defaultPeriod), SOURCE_INPUT],
    outputs: [{ key: 'value', label: name, plot: 'line', color, lineWidth: 2 }],
    warmup: (config) => warmupFor(readPeriod(config, 'period', defaultPeriod)),
    compute: (bars, config) => ({
      values: { value: compute(bars, readPeriod(config, 'period', defaultPeriod), readSource(config)) },
    }),
    short: (config) => `${id.toUpperCase()} ${readPeriod(config, 'period', defaultPeriod)}`,
  };
}

export const TREND_INDICATORS: IndicatorDefinition[] = [
  movingAverage('sma', 'Simple Moving Average', 20, SERIES_COLORS.blue, simpleMovingAverage),
  movingAverage('ema', 'Exponential Moving Average', 20, SERIES_COLORS.gold, exponentialMovingAverage),
  movingAverage('wma', 'Weighted Moving Average', 20, SERIES_COLORS.violet, weightedMovingAverage),
  movingAverage(
    'hma',
    'Hull Moving Average',
    21,
    SERIES_COLORS.teal,
    hullMovingAverage,
    'Near-zero lag; overshoots on reversals by construction.',
    // The sqrt-length WMA runs on the OUTPUT of the full-length one, so the two warm-ups
    // stack rather than overlap.
    (period) => period + Math.round(Math.sqrt(period)),
  ),

  {
    id: 'bbands',
    name: 'Bollinger Bands',
    category: 'trend',
    placement: 'price',
    requires: ['close'],
    inputs: [
      periodInput(20),
      { kind: 'number', key: 'multiplier', label: 'Deviations', default: 2, min: 0.1, max: 6, step: 0.1 },
      SOURCE_INPUT,
    ],
    outputs: [
      { key: 'upper', label: 'Upper', plot: 'line', color: BAND_EDGE, lineWidth: 1 },
      { key: 'middle', label: 'Basis', plot: 'line', color: BAND_MID, lineWidth: 1, lineStyle: 'dashed' },
      { key: 'lower', label: 'Lower', plot: 'line', color: BAND_EDGE, lineWidth: 1 },
    ],
    warmup: (config) => readPeriod(config, 'period', 20),
    compute: (bars, config) => ({
      values: bollingerBands(
        bars,
        readPeriod(config, 'period', 20),
        readNumber(config, 'multiplier', 2),
        readSource(config),
      ),
    }),
    short: (config) => `BB ${readPeriod(config, 'period', 20)} · ${readNumber(config, 'multiplier', 2)}σ`,
  },

  {
    id: 'keltner',
    name: 'Keltner Channels',
    category: 'trend',
    description: 'ATR-width channel around an EMA. Steadier than Bollinger in a squeeze.',
    placement: 'price',
    requires: ['high', 'low', 'close'],
    inputs: [
      periodInput(20),
      { kind: 'number', key: 'atrPeriod', label: 'ATR length', default: 10, min: 1, max: 200, step: 1, advanced: true },
      { kind: 'number', key: 'multiplier', label: 'ATR multiple', default: 2, min: 0.1, max: 10, step: 0.1 },
      SOURCE_INPUT,
    ],
    outputs: [
      { key: 'upper', label: 'Upper', plot: 'line', color: BAND_EDGE, lineWidth: 1 },
      { key: 'middle', label: 'Basis', plot: 'line', color: BAND_MID, lineWidth: 1, lineStyle: 'dashed' },
      { key: 'lower', label: 'Lower', plot: 'line', color: BAND_EDGE, lineWidth: 1 },
    ],
    warmup: (config) => Math.max(readPeriod(config, 'period', 20), readPeriod(config, 'atrPeriod', 10)),
    compute: (bars, config) => ({
      values: keltnerChannels(
        bars,
        readPeriod(config, 'period', 20),
        readPeriod(config, 'atrPeriod', 10),
        readNumber(config, 'multiplier', 2),
        readSource(config),
      ),
    }),
    short: (config) => `KC ${readPeriod(config, 'period', 20)} · ${readNumber(config, 'multiplier', 2)}×ATR`,
  },

  {
    id: 'donchian',
    name: 'Donchian Channels',
    category: 'trend',
    description: 'Highest high and lowest low of the window, current bar included.',
    placement: 'price',
    requires: ['high', 'low'],
    inputs: [periodInput(20)],
    outputs: [
      { key: 'upper', label: 'Upper', plot: 'line', color: BAND_EDGE, lineWidth: 1 },
      { key: 'middle', label: 'Mid', plot: 'line', color: BAND_MID, lineWidth: 1, lineStyle: 'dashed' },
      { key: 'lower', label: 'Lower', plot: 'line', color: BAND_EDGE, lineWidth: 1 },
    ],
    warmup: (config) => readPeriod(config, 'period', 20),
    compute: (bars, config) => ({ values: donchianChannels(bars, readPeriod(config, 'period', 20)) }),
    short: (config) => `DC ${readPeriod(config, 'period', 20)}`,
  },

  {
    id: 'vwap',
    name: 'Rolling VWAP',
    category: 'trend',
    description: 'Volume-weighted average over the last N bars. Not a session VWAP — this chart has no intraday bars.',
    placement: 'price',
    requires: ['high', 'low', 'close', 'volume'],
    inputs: [periodInput(20, 500)],
    outputs: [{ key: 'value', label: 'VWAP', plot: 'line', color: SERIES_COLORS.rose, lineWidth: 2 }],
    warmup: (config) => readPeriod(config, 'period', 20),
    compute: (bars, config) => ({ values: { value: rollingVwap(bars, readPeriod(config, 'period', 20)) } }),
    short: (config) => `VWAP ${readPeriod(config, 'period', 20)}`,
  },

  {
    id: 'supertrend',
    name: 'Supertrend',
    category: 'trend',
    description: 'ATR trailing stop. Green while it trails below price, red while above.',
    placement: 'price',
    requires: ['high', 'low', 'close'],
    inputs: [
      { kind: 'number', key: 'atrPeriod', label: 'ATR length', default: 10, min: 1, max: 200, step: 1 },
      { kind: 'number', key: 'multiplier', label: 'ATR multiple', default: 3, min: 0.1, max: 15, step: 0.1 },
    ],
    outputs: [{ key: 'value', label: 'Supertrend', plot: 'line', color: SERIES_COLORS.up, lineWidth: 2 }],
    warmup: (config) => readPeriod(config, 'atrPeriod', 10),
    compute: (bars, config) => {
      const result = supertrend(bars, readPeriod(config, 'atrPeriod', 10), readNumber(config, 'multiplier', 3));
      return {
        values: { value: result.line },
        // Direction is the indicator's entire message, so it is carried as colour rather than
        // as a second line the operator has to read against the first.
        colors: {
          value: result.direction.map((value) => (value == null ? null : value > 0 ? SERIES_COLORS.up : SERIES_COLORS.down)),
        },
      };
    },
    short: (config) => `ST ${readPeriod(config, 'atrPeriod', 10)} · ${readNumber(config, 'multiplier', 3)}`,
  },
];
