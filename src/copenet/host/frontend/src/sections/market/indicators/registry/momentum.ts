// Momentum and oscillators. Every one of these draws in its own pane.

import {
  averageDirectionalIndex,
  commodityChannelIndex,
  macd,
  moneyFlowIndex,
  rateOfChange,
  relativeStrengthIndex,
  stochastic,
  stochasticRsi,
  williamsR,
} from '../calc/momentum';
import { fisherTransform } from '../calc/ehlers';
import { readPeriod, readSource, readString } from '../config';
import { REFERENCE_LINE, REFERENCE_ZERO, SERIES_COLORS } from '../palette';
import type { IndicatorDefinition, IndicatorInput, IndicatorReference } from '../types';

const SOURCE_INPUT: IndicatorInput = { kind: 'source', key: 'source', label: 'Source', default: 'close', advanced: true };

/** The over/under pair every bounded oscillator is read against. Declared once so RSI, MFI
 *  and the stochastics cannot drift to different levels for the same idea. */
function bounds(high: number, low: number, midline?: number): IndicatorReference[] {
  const references: IndicatorReference[] = [
    { value: high, color: REFERENCE_LINE, lineStyle: 'dashed' },
    { value: low, color: REFERENCE_LINE, lineStyle: 'dashed' },
  ];
  if (midline != null) references.push({ value: midline, color: REFERENCE_ZERO, lineStyle: 'dotted' });
  return references;
}

export const MOMENTUM_INDICATORS: IndicatorDefinition[] = [
  {
    id: 'rsi',
    name: 'Relative Strength Index',
    category: 'momentum',
    placement: 'pane',
    requires: ['close'],
    inputs: [{ kind: 'number', key: 'period', label: 'Length', default: 14, min: 2, max: 200, step: 1 }, SOURCE_INPUT],
    outputs: [{ key: 'rsi', label: 'RSI', plot: 'line', color: SERIES_COLORS.violet, lineWidth: 2 }],
    references: bounds(70, 30, 50),
    paneRange: { min: 0, max: 100 },
    warmup: (config) => readPeriod(config, 'period', 14) + 1,
    compute: (bars, config) => ({
      values: { rsi: relativeStrengthIndex(bars, readPeriod(config, 'period', 14), readSource(config)) },
    }),
    short: (config) => `RSI ${readPeriod(config, 'period', 14)}`,
    format: (value) => value.toFixed(1),
  },

  {
    id: 'stoch',
    name: 'Stochastic Oscillator',
    category: 'momentum',
    description: 'Where the close sits within the recent range. Smoothing 1 is the fast stochastic.',
    placement: 'pane',
    requires: ['high', 'low', 'close'],
    inputs: [
      { kind: 'number', key: 'period', label: '%K length', default: 14, min: 1, max: 200, step: 1 },
      { kind: 'number', key: 'smooth', label: '%K smoothing', default: 3, min: 1, max: 50, step: 1 },
      { kind: 'number', key: 'signal', label: '%D length', default: 3, min: 1, max: 50, step: 1 },
    ],
    outputs: [
      { key: 'k', label: '%K', plot: 'line', color: SERIES_COLORS.blue, lineWidth: 2 },
      { key: 'd', label: '%D', plot: 'line', color: SERIES_COLORS.gold, lineWidth: 1 },
    ],
    references: bounds(80, 20),
    paneRange: { min: 0, max: 100 },
    warmup: (config) => readPeriod(config, 'period', 14) + readPeriod(config, 'smooth', 3) + readPeriod(config, 'signal', 3),
    compute: (bars, config) => ({
      values: stochastic(
        bars,
        readPeriod(config, 'period', 14),
        readPeriod(config, 'smooth', 3),
        readPeriod(config, 'signal', 3),
      ),
    }),
    short: (config) => `Stoch ${readPeriod(config, 'period', 14)}/${readPeriod(config, 'smooth', 3)}/${readPeriod(config, 'signal', 3)}`,
    format: (value) => value.toFixed(1),
  },

  {
    id: 'stochrsi',
    name: 'Stochastic RSI',
    category: 'momentum',
    description: 'Stochastic of RSI rather than of price. Saturates far more often than either input.',
    placement: 'pane',
    requires: ['close'],
    inputs: [
      { kind: 'number', key: 'rsiPeriod', label: 'RSI length', default: 14, min: 2, max: 200, step: 1 },
      { kind: 'number', key: 'stochPeriod', label: 'Stochastic length', default: 14, min: 1, max: 200, step: 1 },
      { kind: 'number', key: 'smooth', label: '%K smoothing', default: 3, min: 1, max: 50, step: 1, advanced: true },
      { kind: 'number', key: 'signal', label: '%D length', default: 3, min: 1, max: 50, step: 1, advanced: true },
      SOURCE_INPUT,
    ],
    outputs: [
      { key: 'k', label: '%K', plot: 'line', color: SERIES_COLORS.blue, lineWidth: 2 },
      { key: 'd', label: '%D', plot: 'line', color: SERIES_COLORS.gold, lineWidth: 1 },
    ],
    references: bounds(80, 20),
    paneRange: { min: 0, max: 100 },
    warmup: (config) =>
      readPeriod(config, 'rsiPeriod', 14)
      + readPeriod(config, 'stochPeriod', 14)
      + readPeriod(config, 'smooth', 3)
      + readPeriod(config, 'signal', 3),
    compute: (bars, config) => ({
      values: stochasticRsi(
        bars,
        readPeriod(config, 'rsiPeriod', 14),
        readPeriod(config, 'stochPeriod', 14),
        readPeriod(config, 'smooth', 3),
        readPeriod(config, 'signal', 3),
        readSource(config),
      ),
    }),
    short: (config) => `StochRSI ${readPeriod(config, 'rsiPeriod', 14)}/${readPeriod(config, 'stochPeriod', 14)}`,
    format: (value) => value.toFixed(1),
  },

  {
    id: 'macd',
    name: 'MACD',
    category: 'momentum',
    placement: 'pane',
    requires: ['close'],
    inputs: [
      { kind: 'number', key: 'fast', label: 'Fast length', default: 12, min: 1, max: 200, step: 1 },
      { kind: 'number', key: 'slow', label: 'Slow length', default: 26, min: 2, max: 400, step: 1 },
      { kind: 'number', key: 'signal', label: 'Signal length', default: 9, min: 1, max: 200, step: 1 },
      SOURCE_INPUT,
    ],
    outputs: [
      { key: 'histogram', label: 'Histogram', plot: 'histogram', color: SERIES_COLORS.slate },
      { key: 'macd', label: 'MACD', plot: 'line', color: SERIES_COLORS.blue, lineWidth: 2 },
      { key: 'signal', label: 'Signal', plot: 'line', color: SERIES_COLORS.gold, lineWidth: 1 },
    ],
    references: [{ value: 0, color: REFERENCE_ZERO }],
    warmup: (config) => readPeriod(config, 'slow', 26) + readPeriod(config, 'signal', 9),
    compute: (bars, config) => {
      const result = macd(
        bars,
        readPeriod(config, 'fast', 12),
        readPeriod(config, 'slow', 26),
        readPeriod(config, 'signal', 9),
        readSource(config),
      );
      return {
        values: result,
        colors: {
          histogram: result.histogram.map((value) => (value == null ? null : value >= 0 ? SERIES_COLORS.up : SERIES_COLORS.down)),
        },
      };
    },
    short: (config) => `MACD ${readPeriod(config, 'fast', 12)}/${readPeriod(config, 'slow', 26)}/${readPeriod(config, 'signal', 9)}`,
  },

  {
    id: 'roc',
    name: 'Rate of Change',
    category: 'momentum',
    description: 'Percent change over N bars, or the raw price difference.',
    placement: 'pane',
    requires: ['close'],
    inputs: [
      { kind: 'number', key: 'period', label: 'Length', default: 12, min: 1, max: 400, step: 1 },
      {
        kind: 'enum',
        key: 'mode',
        label: 'Scale',
        default: 'percent',
        choices: [
          { value: 'percent', label: 'Percent' },
          { value: 'difference', label: 'Price difference' },
        ],
      },
      SOURCE_INPUT,
    ],
    outputs: [{ key: 'roc', label: 'ROC', plot: 'line', color: SERIES_COLORS.teal, lineWidth: 2 }],
    references: [{ value: 0, color: REFERENCE_ZERO }],
    warmup: (config) => readPeriod(config, 'period', 12) + 1,
    compute: (bars, config) => ({
      values: {
        roc: rateOfChange(
          bars,
          readPeriod(config, 'period', 12),
          readString(config, 'mode', 'percent') === 'difference' ? 'difference' : 'percent',
          readSource(config),
        ),
      },
    }),
    short: (config) => `ROC ${readPeriod(config, 'period', 12)}`,
    format: (value, config) =>
      readString(config, 'mode', 'percent') === 'difference' ? value.toFixed(2) : `${value.toFixed(2)}%`,
  },

  {
    id: 'cci',
    name: 'Commodity Channel Index',
    category: 'momentum',
    placement: 'pane',
    requires: ['high', 'low', 'close'],
    inputs: [{ kind: 'number', key: 'period', label: 'Length', default: 20, min: 2, max: 400, step: 1 }],
    outputs: [{ key: 'cci', label: 'CCI', plot: 'line', color: SERIES_COLORS.rose, lineWidth: 2 }],
    references: bounds(100, -100, 0),
    warmup: (config) => readPeriod(config, 'period', 20),
    compute: (bars, config) => ({ values: { cci: commodityChannelIndex(bars, readPeriod(config, 'period', 20)) } }),
    short: (config) => `CCI ${readPeriod(config, 'period', 20)}`,
    format: (value) => value.toFixed(1),
  },

  {
    id: 'willr',
    name: 'Williams %R',
    category: 'momentum',
    placement: 'pane',
    requires: ['high', 'low', 'close'],
    inputs: [{ kind: 'number', key: 'period', label: 'Length', default: 14, min: 1, max: 400, step: 1 }],
    outputs: [{ key: 'willr', label: '%R', plot: 'line', color: SERIES_COLORS.violet, lineWidth: 2 }],
    references: bounds(-20, -80),
    paneRange: { min: -100, max: 0 },
    warmup: (config) => readPeriod(config, 'period', 14),
    compute: (bars, config) => ({ values: { willr: williamsR(bars, readPeriod(config, 'period', 14)) } }),
    short: (config) => `%R ${readPeriod(config, 'period', 14)}`,
    format: (value) => value.toFixed(1),
  },

  {
    id: 'adx',
    name: 'ADX / DMI',
    category: 'momentum',
    description: 'Trend strength with its direction pair. ADX above 25 is the usual trending threshold.',
    placement: 'pane',
    requires: ['high', 'low', 'close'],
    inputs: [
      { kind: 'number', key: 'period', label: 'DI length', default: 14, min: 1, max: 200, step: 1 },
      { kind: 'number', key: 'adxPeriod', label: 'ADX smoothing', default: 14, min: 1, max: 200, step: 1, advanced: true },
    ],
    outputs: [
      { key: 'adx', label: 'ADX', plot: 'line', color: SERIES_COLORS.sand, lineWidth: 2 },
      { key: 'plusDi', label: '+DI', plot: 'line', color: SERIES_COLORS.up, lineWidth: 1 },
      { key: 'minusDi', label: '−DI', plot: 'line', color: SERIES_COLORS.down, lineWidth: 1 },
    ],
    references: [{ value: 25, color: REFERENCE_LINE, lineStyle: 'dashed' }],
    paneRange: { min: 0, max: 100 },
    warmup: (config) => readPeriod(config, 'period', 14) + readPeriod(config, 'adxPeriod', 14),
    compute: (bars, config) => ({
      values: averageDirectionalIndex(bars, readPeriod(config, 'period', 14), readPeriod(config, 'adxPeriod', 14)),
    }),
    short: (config) => `ADX ${readPeriod(config, 'period', 14)}`,
    format: (value) => value.toFixed(1),
  },

  {
    id: 'mfi',
    name: 'Money Flow Index',
    category: 'momentum',
    description: 'RSI weighted by volume. Blank when the instrument reports no volume.',
    placement: 'pane',
    requires: ['high', 'low', 'close', 'volume'],
    inputs: [{ kind: 'number', key: 'period', label: 'Length', default: 14, min: 2, max: 200, step: 1 }],
    outputs: [{ key: 'mfi', label: 'MFI', plot: 'line', color: SERIES_COLORS.teal, lineWidth: 2 }],
    references: bounds(80, 20, 50),
    paneRange: { min: 0, max: 100 },
    warmup: (config) => readPeriod(config, 'period', 14) + 1,
    compute: (bars, config) => ({ values: { mfi: moneyFlowIndex(bars, readPeriod(config, 'period', 14)) } }),
    short: (config) => `MFI ${readPeriod(config, 'period', 14)}`,
    format: (value) => value.toFixed(1),
  },

  {
    id: 'fisher',
    name: 'Fisher Transform',
    category: 'ehlers',
    description: 'Gaussianises the price distribution so turns become sharp peaks.',
    placement: 'pane',
    requires: ['high', 'low'],
    inputs: [
      { kind: 'number', key: 'period', label: 'Length', default: 9, min: 2, max: 200, step: 1 },
      { kind: 'source', key: 'source', label: 'Source', default: 'hl2', advanced: true },
    ],
    outputs: [
      { key: 'fisher', label: 'Fisher', plot: 'line', color: SERIES_COLORS.blue, lineWidth: 2 },
      { key: 'trigger', label: 'Trigger', plot: 'line', color: SERIES_COLORS.gold, lineWidth: 1 },
    ],
    references: [{ value: 0, color: REFERENCE_ZERO }],
    warmup: (config) => readPeriod(config, 'period', 9),
    compute: (bars, config) => ({
      values: fisherTransform(bars, readPeriod(config, 'period', 9), readSource(config, 'source', 'hl2')),
    }),
    short: (config) => `Fisher ${readPeriod(config, 'period', 9)}`,
    format: (value) => value.toFixed(3),
  },
];
