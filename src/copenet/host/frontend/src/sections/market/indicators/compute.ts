// Turning configured instances into drawable series.
//
// Two things happen here and nowhere else.
//
// FULL HISTORY, THEN SLICE. Indicators are computed over every bar the payload carries, and
// only then cut to the visible range. Computing over the visible bars instead would restart
// every warm-up on each range change, so switching 1Y to 6M would silently delete the first
// 20 bars of an EMA and redraw the rest at different values. Because every calculation is
// causal (asserted registry-wide in the tests), the slice is exact rather than approximate.
//
// MEMOISED BY CONFIGURATION, NOT BY INSTANCE. The cache key is the indicator id, its config
// and the identity of the bar series. Opening a popover, hovering the chart or changing an
// unrelated indicator's colour therefore recomputes nothing, and two instances configured
// identically compute once.

import { indicatorById } from './registry';
import { instanceComputeKey, type IndicatorInstance } from './state';
import type {
  IndicatorBar,
  IndicatorContext,
  IndicatorDefinition,
  IndicatorResult,
  IndicatorSeries,
} from './types';

export interface IndicatorPoint {
  t: number;
  value: number;
  color?: string;
}

export interface ComputedOutput {
  key: string;
  label: string;
  plot: IndicatorDefinition['outputs'][number]['plot'];
  color: string;
  lineWidth: number;
  lineStyle: 'solid' | 'dashed' | 'dotted';
  points: IndicatorPoint[];
  /** Last computable value in the visible range, already formatted for the legend. */
  latest: string | null;
}

export interface ComputedIndicator {
  instanceId: string;
  indicatorId: string;
  definition: IndicatorDefinition;
  /** The configured instance behind this result. Carried so a control surface can render a
   *  settings form without a second lookup against the layout. */
  instance: IndicatorInstance;
  label: string;
  visible: boolean;
  placement: 'price' | 'pane';
  outputs: ComputedOutput[];
  references: IndicatorDefinition['references'];
  paneRange: IndicatorDefinition['paneRange'];
  /** True when the loaded history is shorter than the indicator needs. Drives the notice. */
  insufficientHistory: boolean;
}

export interface IndicatorComputer {
  compute(
    /** Every bar the payload carries, at the current interval. */
    history: IndicatorBar[],
    /** How many bars at the tail of `history` the chart is currently showing. */
    visibleCount: number,
    instances: IndicatorInstance[],
    context: IndicatorContext,
  ): ComputedIndicator[];
}

export function createIndicatorComputer(): IndicatorComputer {
  const cache = new Map<string, IndicatorResult>();
  const seriesIds = new WeakMap<IndicatorBar[], number>();
  let nextSeriesId = 1;

  /** Market payloads replace their bar arrays rather than mutating them. Keying the memo by
   *  that immutable series identity catches every kind of refresh — including a high, low,
   *  or volume revision on an unchanged closing price — without hashing the full history. */
  const barsIdentity = (bars: IndicatorBar[]): number => {
    const existing = seriesIds.get(bars);
    if (existing != null) return existing;
    const identity = nextSeriesId;
    nextSeriesId += 1;
    seriesIds.set(bars, identity);
    return identity;
  };

  return {
    compute(history, visibleCount, instances, context) {
      const identity = barsIdentity(history);
      const live = new Set<string>();
      const computed: ComputedIndicator[] = [];

      for (const instance of instances) {
        const definition = indicatorById(instance.indicatorId);
        if (!definition) continue;

        const key = `${identity}|${instanceComputeKey(instance)}|${context.barsPerYear}`;
        live.add(key);
        let result = cache.get(key);
        if (!result) {
          result = definition.compute(history, instance.config, context);
          cache.set(key, result);
        }

        // The visible window is a suffix of the full history, so a single offset aligns
        // every output without searching for timestamps.
        const offset = Math.max(0, history.length - visibleCount);
        const visibleBars = history.slice(offset);

        const outputs = definition.outputs.map((output) => {
          const style = instance.styles?.[output.key];
          const values: IndicatorSeries = result.values[output.key] ?? [];
          const colors = result.colors?.[output.key];
          const points: IndicatorPoint[] = [];
          for (let i = offset; i < history.length; i += 1) {
            const value = values[i];
            if (value == null || !Number.isFinite(value)) continue;
            const perBarColor = colors?.[i];
            points.push(perBarColor ? { t: history[i].t, value, color: perBarColor } : { t: history[i].t, value });
          }
          const lastValue = points.length ? points[points.length - 1].value : null;
          return {
            key: output.key,
            label: output.label,
            plot: output.plot,
            color: style?.color ?? output.color,
            lineWidth: style?.lineWidth ?? output.lineWidth ?? 2,
            lineStyle: style?.lineStyle ?? output.lineStyle ?? 'solid',
            points,
            latest: lastValue == null
              ? null
              : definition.format
                ? definition.format(lastValue, instance.config)
                : defaultFormat(lastValue),
          } satisfies ComputedOutput;
        });

        computed.push({
          instanceId: instance.instanceId,
          indicatorId: instance.indicatorId,
          definition,
          instance,
          label: definition.short(instance.config),
          visible: instance.visible,
          placement: definition.placement,
          outputs,
          references: definition.references,
          paneRange: definition.paneRange,
          // Judged against the VISIBLE bar count, because that is what the operator can see
          // being empty. The calculation itself still had the full history to work from.
          insufficientHistory: visibleBars.length > 0 && outputs.every((output) => output.points.length === 0),
        });
      }

      // Drop everything this pass did not touch. Without the sweep the cache grows by one
      // entry per bar update per instance and never shrinks.
      for (const key of [...cache.keys()]) {
        if (!live.has(key)) cache.delete(key);
      }
      return computed;
    },
  };
}

/** Legend ordering, which is NOT draw ordering.
 *
 *  Outputs are declared in the order they must be drawn — MACD's histogram is declared first
 *  so the two lines paint over it rather than under. Reading order is the opposite: the line
 *  is the indicator's headline number and the histogram is derived from it, so a legend led
 *  by the histogram invites the wrong number to be read as the MACD value. */
export function legendOutputs(indicator: ComputedIndicator): ComputedOutput[] {
  const rank = (output: ComputedOutput) => (output.plot === 'histogram' ? 1 : 0);
  return [...indicator.outputs].sort((left, right) => rank(left) - rank(right));
}

/** The colour that identifies the indicator: its first line, or its only series. */
export function legendColor(indicator: ComputedIndicator): string | undefined {
  return legendOutputs(indicator)[0]?.color;
}

function defaultFormat(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (magnitude >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (magnitude >= 1000) return value.toFixed(0);
  if (magnitude >= 1) return value.toFixed(2);
  return value.toFixed(4);
}

/** Bars per year for the chart's interval, so annualising indicators do not assume daily. */
export function barsPerYear(timeframe: 'D' | 'W' | 'M'): number {
  return timeframe === 'D' ? 252 : timeframe === 'W' ? 52 : 12;
}
