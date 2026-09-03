/** The background evaluator uses exactly the chart registry, never a second formula set. */
import { indicatorById } from './registry';
import { defaultConfig, normalizeConfig } from './config';
import type { IndicatorBar, IndicatorConfig } from './types';

export const ALERT_INDICATOR_IDS = ['sma', 'ema', 'rsi', 'macd'] as const;
export type AlertOperand = { kind: 'price' } | { kind: 'constant'; value: number }
  | { kind: 'indicator'; indicatorId: string; config: IndicatorConfig; output: string };

export function alertCatalogue() {
  return ALERT_INDICATOR_IDS.map((id) => {
    const definition = indicatorById(id)!;
    return { id, name: definition.name, inputs: definition.inputs, outputs: definition.outputs,
      defaults: defaultConfig(definition), warmup: definition.warmup(defaultConfig(definition)) };
  });
}

export function validateOperand(raw: unknown): AlertOperand {
  if (!raw || typeof raw !== 'object') throw new Error('An operand is required');
  const operand = raw as Record<string, unknown>;
  if (operand.kind === 'price') return { kind: 'price' };
  if (operand.kind === 'constant' && typeof operand.value === 'number' && Number.isFinite(operand.value)) {
    return { kind: 'constant', value: operand.value };
  }
  if (operand.kind !== 'indicator' || !ALERT_INDICATOR_IDS.includes(operand.indicatorId as typeof ALERT_INDICATOR_IDS[number])) {
    throw new Error('Unsupported alert operand');
  }
  const definition = indicatorById(operand.indicatorId as string)!;
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

export function evaluateAlertRequest(raw: Record<string, unknown>) {
  if (raw.action === 'catalogue') return { indicators: alertCatalogue() };
  const left = validateOperand(raw.left), right = validateOperand(raw.right);
  if (left.kind === 'constant' && right.kind === 'constant') throw new Error('At least one operand must observe the market');
  if (raw.action === 'validate') return { left, right };
  if (!Array.isArray(raw.bars) || raw.bars.length > 30000) throw new Error('Expected at most 30000 candles');
  const bars = raw.bars as IndicatorBar[];
  for (let i = 0; i < bars.length; i++) {
    if (!['t', 'o', 'h', 'l', 'c', 'v'].every((key) => typeof bars[i]?.[key] === 'number' && Number.isFinite(bars[i][key]))) throw new Error('Invalid candle');
    if (i && bars[i].t <= bars[i - 1].t) throw new Error('Candles must be strictly ordered');
  }
  const periods = { daily: 252, weekly: 52, monthly: 12 };
  if (!(String(raw.timeframe) in periods)) throw new Error('Unsupported timeframe');
  const context = periods[String(raw.timeframe) as keyof typeof periods];
  const lhs = evaluateOperand(bars, left, context), rhs = evaluateOperand(bars, right, context);
  return { points: bars.map((bar, index) => ({ t: bar.t, left: lhs[index] ?? null, right: rhs[index] ?? null })) };
}
