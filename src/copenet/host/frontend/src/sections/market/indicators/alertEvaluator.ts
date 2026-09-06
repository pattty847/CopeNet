/** The background evaluator uses exactly the chart registry, never a second formula set. */
import { INDICATORS, indicatorById } from './registry';
import { defaultConfig, normalizeConfig } from './config';
import type { IndicatorBar, IndicatorConfig } from './types';

export type AlertOperand = { kind: 'price' } | { kind: 'constant'; value: number }
  | { kind: 'indicator'; indicatorId: string; config: IndicatorConfig; output: string };

/** Every registry indicator is alertable. There is deliberately no second allowlist: the
 *  registry already guarantees what an alert needs — a pure, causal calculation that returns
 *  null (never NaN) where it has no value, and a declared warm-up. A hand-maintained subset
 *  could only ever drift behind it, which is how MAMA/FAMA came to be plotted on the chart
 *  but unreachable from an alert. */
export function alertCatalogue() {
  return INDICATORS.map((definition) => ({
    id: definition.id, name: definition.name, inputs: definition.inputs, outputs: definition.outputs,
    defaults: defaultConfig(definition), warmup: definition.warmup(defaultConfig(definition)),
  }));
}

export function validateOperand(raw: unknown): AlertOperand {
  if (!raw || typeof raw !== 'object') throw new Error('An operand is required');
  const operand = raw as Record<string, unknown>;
  if (operand.kind === 'price') return { kind: 'price' };
  if (operand.kind === 'constant' && typeof operand.value === 'number' && Number.isFinite(operand.value)) {
    return { kind: 'constant', value: operand.value };
  }
  if (operand.kind !== 'indicator' || typeof operand.indicatorId !== 'string') throw new Error('Unsupported alert operand');
  const definition = indicatorById(operand.indicatorId);
  if (!definition) throw new Error('Unsupported alert operand');
  if (!definition.outputs.some((output) => output.key === operand.output)) throw new Error('Invalid indicator output');
  const config = normalizeConfig(definition, operand.config);
  if (operand.config && (typeof operand.config !== 'object' || Array.isArray(operand.config))) throw new Error('Invalid indicator config');
  for (const [key, value] of Object.entries(operand.config ?? {})) {
    if (!(key in config) || config[key] !== value) throw new Error(`Invalid indicator setting: ${key}`);
  }
  return { kind: 'indicator', indicatorId: definition.id, output: operand.output as string, config };
}

export function evaluateOperand(bars: IndicatorBar[], operand: AlertOperand, barsPerYear: number): (number | null)[] {
  if (operand.kind === 'constant') return bars.map(() => operand.value);
  if (operand.kind === 'price') return bars.map((bar) => bar.c);
  return indicatorById(operand.indicatorId)!.compute(bars, operand.config, { barsPerYear }).values[operand.output];
}

/** One indicator to evaluate against one symbol's bars. */
export type IndicatorSpec = { indicatorId: string; config: IndicatorConfig };

/** One symbol's final-bar reading. `error` is per symbol, never for the whole batch. */
export type LatestResult = {
  key: string;
  t: number | null;
  values: Record<string, Record<string, number | null>>;
  error: string | null;
};

function validateIndicatorSpec(raw: unknown): IndicatorSpec {
  if (!raw || typeof raw !== 'object') throw new Error('An indicator is required');
  const spec = raw as Record<string, unknown>;
  if (typeof spec.indicatorId !== 'string') throw new Error('Unsupported indicator');
  const definition = indicatorById(spec.indicatorId);
  if (!definition) throw new Error('Unsupported indicator');
  if (spec.config && (typeof spec.config !== 'object' || Array.isArray(spec.config))) throw new Error('Invalid indicator config');
  const config = normalizeConfig(definition, spec.config as IndicatorConfig | undefined);
  for (const [key, value] of Object.entries((spec.config ?? {}) as IndicatorConfig)) {
    if (!(key in config) || config[key] !== value) throw new Error(`Invalid indicator setting: ${key}`);
  }
  return { indicatorId: definition.id, config };
}

function validateBars(raw: unknown): IndicatorBar[] {
  if (!Array.isArray(raw) || raw.length > 30000) throw new Error('Expected at most 30000 candles');
  const bars = raw as IndicatorBar[];
  for (let i = 0; i < bars.length; i++) {
    if (!['t', 'o', 'h', 'l', 'c', 'v'].every((key) => typeof bars[i]?.[key] === 'number' && Number.isFinite(bars[i][key]))) throw new Error('Invalid candle');
    if (i && bars[i].t <= bars[i - 1].t) throw new Error('Candles must be strictly ordered');
  }
  return bars;
}

const BARS_PER_YEAR: Record<string, number> = { daily: 252, weekly: 52, monthly: 12 };

/** Evaluate indicators for many symbols in ONE process, returning only each one's final bar.
 *
 *  A per-symbol subprocess costs ~80ms of Node startup, which is tolerable for one ticker and
 *  not for a universe sweep. Returning only the last point is what keeps the response bounded:
 *  the callers this exists for — the MAMA/FAMA regime, and breadth counted across constituents
 *  — ask "where does this symbol stand now", never for the whole series. Full history still
 *  goes IN, because these are recursive filters whose value depends on their seed, and a
 *  truncated window would quietly disagree with the chart.
 *
 *  One bad symbol reports its own error rather than failing the batch. A sweep that loses a
 *  whole chunk to one malformed frame is how a breadth number silently loses its denominator.
 */
export function evaluateLatestRequest(raw: Record<string, unknown>) {
  const timeframe = String(raw.timeframe);
  if (!(timeframe in BARS_PER_YEAR)) throw new Error('Unsupported timeframe');
  const barsPerYear = BARS_PER_YEAR[timeframe];
  if (!Array.isArray(raw.requests) || !raw.requests.length || raw.requests.length > 1000) {
    throw new Error('Expected 1-1000 symbol requests');
  }
  const results: LatestResult[] = (raw.requests as Record<string, unknown>[]).map((request): LatestResult => {
    const key = String(request?.key ?? '');
    try {
      const specs = (Array.isArray(request.indicators) ? request.indicators : []).map(validateIndicatorSpec);
      if (!specs.length) throw new Error('At least one indicator is required');
      const bars = validateBars(request.bars);
      if (!bars.length) return { key, t: null, values: {}, error: null };
      const values: Record<string, Record<string, number | null>> = {};
      for (const spec of specs) {
        const computed = indicatorById(spec.indicatorId)!.compute(bars, spec.config, { barsPerYear }).values;
        values[spec.indicatorId] = Object.fromEntries(
          Object.entries(computed).map(([output, series]) => [output, series[bars.length - 1] ?? null]),
        );
      }
      return { key, t: bars[bars.length - 1].t, values, error: null };
    } catch (error) {
      return { key, t: null, values: {}, error: error instanceof Error ? error.message : 'Evaluation failed' };
    }
  });
  return { results };
}

export function evaluateAlertRequest(raw: Record<string, unknown>) {
  if (raw.action === 'catalogue') return { indicators: alertCatalogue() };
  if (raw.action === 'latest') return evaluateLatestRequest(raw);
  const left = validateOperand(raw.left), right = validateOperand(raw.right);
  if (left.kind === 'constant' && right.kind === 'constant') throw new Error('At least one operand must observe the market');
  if (raw.action === 'validate') return { left, right };
  const bars = validateBars(raw.bars);
  if (!(String(raw.timeframe) in BARS_PER_YEAR)) throw new Error('Unsupported timeframe');
  const context = BARS_PER_YEAR[String(raw.timeframe)];
  const lhs = evaluateOperand(bars, left, context), rhs = evaluateOperand(bars, right, context);
  return { points: bars.map((bar, index) => ({ t: bar.t, left: lhs[index] ?? null, right: rhs[index] ?? null })) };
}
