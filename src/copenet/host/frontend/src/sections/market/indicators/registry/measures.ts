// Volatility, range and volume-flow. All draw in their own pane.

import { averageRangePercent, averageTrueRange, historicalVolatility } from '../calc/volatility';
import { chaikinMoneyFlow, onBalanceVolume } from '../calc/volume';
import { readPeriod, readString } from '../config';
import { REFERENCE_LINE, REFERENCE_ZERO, SERIES_COLORS } from '../palette';
import { formatIndicatorValue } from '../palette';
import type { IndicatorDefinition } from '../types';

export const MEASURE_INDICATORS: IndicatorDefinition[] = [
  {
    id: 'atr',
    name: 'Average True Range',
    category: 'volatility',
    description: 'Gap-aware range in price units. Use ADR% to compare across instruments.',
    placement: 'pane',
    requires: ['high', 'low', 'close'],
    inputs: [{ kind: 'number', key: 'period', label: 'Length', default: 14, min: 1, max: 200, step: 1 }],
    outputs: [{ key: 'atr', label: 'ATR', plot: 'line', color: SERIES_COLORS.sand, lineWidth: 2 }],
    warmup: (config) => readPeriod(config, 'period', 14),
    compute: (bars, config) => ({ values: { atr: averageTrueRange(bars, readPeriod(config, 'period', 14)) } }),
    short: (config) => `ATR ${readPeriod(config, 'period', 14)}`,
  },

  {
    id: 'adr',
    name: 'Average Range %',
    category: 'volatility',
    description: 'Mean high/low excursion per bar, scale-free. Reads per-bar, so it is not a daily figure on a weekly chart.',
    placement: 'pane',
    requires: ['high', 'low'],
    inputs: [{ kind: 'number', key: 'period', label: 'Length', default: 20, min: 1, max: 400, step: 1 }],
    outputs: [{ key: 'adr', label: 'ADR%', plot: 'line', color: SERIES_COLORS.gold, lineWidth: 2 }],
    warmup: (config) => readPeriod(config, 'period', 20),
    compute: (bars, config) => ({ values: { adr: averageRangePercent(bars, readPeriod(config, 'period', 20)) } }),
    short: (config) => `ADR% ${readPeriod(config, 'period', 20)}`,
    format: (value) => `${value.toFixed(2)}%`,
  },

  {
    id: 'hv',
    name: 'Historical Volatility',
    category: 'volatility',
    description: 'Annualised standard deviation of log returns.',
    placement: 'pane',
    requires: ['close'],
    inputs: [
      { kind: 'number', key: 'period', label: 'Length', default: 20, min: 2, max: 400, step: 1 },
      {
        kind: 'enum',
        key: 'basis',
        label: 'Annualise by',
        default: 'auto',
        choices: [
          { value: 'auto', label: 'Chart interval' },
          { value: '252', label: 'Daily (252)' },
          { value: '52', label: 'Weekly (52)' },
          { value: '12', label: 'Monthly (12)' },
        ],
        advanced: true,
      },
    ],
    outputs: [{ key: 'hv', label: 'HV', plot: 'line', color: SERIES_COLORS.rose, lineWidth: 2 }],
    warmup: (config) => readPeriod(config, 'period', 20) + 1,
    compute: (bars, config, context) => ({
      values: {
        hv: historicalVolatility(bars, readPeriod(config, 'period', 20), readString(config, 'basis', 'auto'), context),
      },
    }),
    short: (config) => `HV ${readPeriod(config, 'period', 20)}`,
    format: (value) => `${value.toFixed(1)}%`,
  },

  {
    id: 'obv',
    name: 'On-Balance Volume',
    category: 'volume',
    description: 'Running volume total. Only the shape is meaningful — the level depends on where history starts.',
    placement: 'pane',
    requires: ['close', 'volume'],
    inputs: [],
    outputs: [{ key: 'obv', label: 'OBV', plot: 'line', color: SERIES_COLORS.blue, lineWidth: 2 }],
    warmup: () => 1,
    compute: (bars) => ({ values: { obv: onBalanceVolume(bars) } }),
    short: () => 'OBV',
    format: (value) => formatIndicatorValue(value),
  },

  {
    id: 'cmf',
    name: 'Chaikin Money Flow',
    category: 'volume',
    description: 'Volume weighted by where each bar closed in its own range. Bounded to ±1.',
    placement: 'pane',
    requires: ['high', 'low', 'close', 'volume'],
    inputs: [{ kind: 'number', key: 'period', label: 'Length', default: 20, min: 1, max: 400, step: 1 }],
    outputs: [{ key: 'cmf', label: 'CMF', plot: 'histogram', color: SERIES_COLORS.teal }],
    references: [
      { value: 0, color: REFERENCE_ZERO },
      { value: 0.05, color: REFERENCE_LINE, lineStyle: 'dotted' },
      { value: -0.05, color: REFERENCE_LINE, lineStyle: 'dotted' },
    ],
    paneRange: { min: -1, max: 1 },
    warmup: (config) => readPeriod(config, 'period', 20),
    compute: (bars, config) => {
      const values = chaikinMoneyFlow(bars, readPeriod(config, 'period', 20));
      return {
        values: { cmf: values },
        colors: {
          cmf: values.map((value) => (value == null ? null : value >= 0 ? SERIES_COLORS.up : SERIES_COLORS.down)),
        },
      };
    },
    short: (config) => `CMF ${readPeriod(config, 'period', 20)}`,
    format: (value) => value.toFixed(3),
  },
];
