// Ehlers overlays. The Fisher Transform lives with the oscillators because it draws in a
// pane; these three draw on price.

import { instantaneousTrendline, mesaAdaptiveMovingAverage, superSmoother } from '../calc/ehlers';
import { readNumber, readPeriod, readSource } from '../config';
import { SERIES_COLORS } from '../palette';
import type { IndicatorDefinition, IndicatorInput } from '../types';

const SOURCE_INPUT: IndicatorInput = { kind: 'source', key: 'source', label: 'Source', default: 'close', advanced: true };

export const EHLERS_INDICATORS: IndicatorDefinition[] = [
  {
    id: 'supersmoother',
    name: 'Super Smoother',
    category: 'ehlers',
    description: 'Two-pole low-pass filter. Far less lag than an SMA of the same length, and no ringing.',
    placement: 'price',
    requires: ['close'],
    inputs: [{ kind: 'number', key: 'period', label: 'Length', default: 10, min: 2, max: 200, step: 1 }, SOURCE_INPUT],
    outputs: [{ key: 'value', label: 'Super Smoother', plot: 'line', color: SERIES_COLORS.teal, lineWidth: 2 }],
    // Seeded from the first bar rather than gated: the filter converges within a few bars and
    // Ehlers' own implementation reads it from the start.
    warmup: () => 1,
    compute: (bars, config) => ({
      values: { value: superSmoother(bars, readPeriod(config, 'period', 10), readSource(config)) },
    }),
    short: (config) => `SSF ${readPeriod(config, 'period', 10)}`,
  },

  {
    id: 'mama',
    name: 'MAMA / FAMA',
    category: 'ehlers',
    description: 'Adaptive average driven by the measured dominant cycle. The crossover is the signal.',
    placement: 'price',
    requires: ['close'],
    inputs: [
      { kind: 'number', key: 'fastLimit', label: 'Fast limit', default: 0.5, min: 0.01, max: 0.99, step: 0.01 },
      { kind: 'number', key: 'slowLimit', label: 'Slow limit', default: 0.05, min: 0.001, max: 0.99, step: 0.005 },
      {
        kind: 'number',
        key: 'warmup',
        label: 'Settling bars',
        default: 32,
        min: 6,
        max: 200,
        step: 1,
        advanced: true,
      },
      SOURCE_INPUT,
    ],
    outputs: [
      { key: 'mama', label: 'MAMA', plot: 'line', color: SERIES_COLORS.blue, lineWidth: 2 },
      { key: 'fama', label: 'FAMA', plot: 'line', color: SERIES_COLORS.gold, lineWidth: 1 },
    ],
    warmup: (config) => readPeriod(config, 'warmup', 32),
    compute: (bars, config) => {
      const result = mesaAdaptiveMovingAverage(
        bars,
        readNumber(config, 'fastLimit', 0.5),
        readNumber(config, 'slowLimit', 0.05),
        readPeriod(config, 'warmup', 32),
        readSource(config),
      );
      return { values: { mama: result.mama, fama: result.fama } };
    },
    short: () => 'MAMA / FAMA',
  },

  {
    id: 'itrend',
    name: 'Instantaneous Trendline',
    category: 'ehlers',
    description: 'Near-zero-lag trendline with a two-bar extrapolation trigger.',
    placement: 'price',
    requires: ['close'],
    inputs: [
      { kind: 'number', key: 'alpha', label: 'Alpha', default: 0.07, min: 0.01, max: 0.99, step: 0.01 },
      SOURCE_INPUT,
    ],
    outputs: [
      { key: 'trend', label: 'Trendline', plot: 'line', color: SERIES_COLORS.violet, lineWidth: 2 },
      { key: 'trigger', label: 'Trigger', plot: 'line', color: SERIES_COLORS.sand, lineWidth: 1, lineStyle: 'dashed' },
    ],
    // Bars 0-6 use Ehlers' seed average; the trigger spans two bars, so three is the first
    // point at which BOTH outputs exist.
    warmup: () => 3,
    compute: (bars, config) => ({
      values: instantaneousTrendline(bars, readNumber(config, 'alpha', 0.07), readSource(config)),
    }),
    short: (config) => `ITrend ${readNumber(config, 'alpha', 0.07)}`,
  },
];
