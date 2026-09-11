// Every screener rule is a bounded window on one candidate field. The table draws each
// value as a tick inside that window, so "why it matched" is visible per row instead of
// hidden behind a disclosure. Windows are declared here, next to the preset ids they
// belong to; the backend's `evaluate.py` is the authority on the boundaries themselves.
import type { Candidate, Preset } from './types';

export type RuleKey =
  | 'bandWidth'
  | 'drawdown'
  | 'rsi'
  | 'distance50'
  | 'distance200'
  | 'monthReturn'
  | 'relativeVolume'
  | 'change'
  | 'marketCap';

export type RuleWindow = {
  key: RuleKey;
  label: string;
  condition: string;
  /** Inclusive bounds of the drawn window. `null` means the rule has no drawable range. */
  low: number | null;
  high: number | null;
  unit: '%' | '' | '×' | '$';
};

const RSI = (low: number, high: number): RuleWindow => ({
  key: 'rsi',
  label: 'RSI (14)',
  condition: `${low} – ${high}`,
  low,
  high,
  unit: '',
});

export const RULE_WINDOWS: Record<string, RuleWindow[]> = {
  compression: [
    { key: 'bandWidth', label: 'Band width', condition: '≤ 10% of price', low: 0, high: 10, unit: '%' },
    { key: 'drawdown', label: 'From 52w high', condition: '0 to −10%', low: -10, high: 0, unit: '%' },
    RSI(40, 65),
  ],
  pullback: [
    { key: 'distance50', label: 'From SMA50', condition: '−2% to +4%', low: -2, high: 4, unit: '%' },
    { key: 'distance200', label: 'Over SMA200', condition: '> 0, SMA50 > SMA200', low: 0, high: 30, unit: '%' },
    { key: 'drawdown', label: 'From 52w high', condition: '−3% to −15%', low: -15, high: -3, unit: '%' },
    RSI(40, 60),
  ],
  oversold: [
    RSI(25, 38),
    { key: 'drawdown', label: 'From 52w high', condition: '−15% to −40%', low: -40, high: -15, unit: '%' },
    { key: 'marketCap', label: 'Market cap', condition: '≥ $15B', low: null, high: null, unit: '$' },
  ],
  breakdown: [
    { key: 'distance200', label: 'Under SMA200', condition: '0 to −15%', low: -15, high: 0, unit: '%' },
    { key: 'distance50', label: 'Under SMA50', condition: '< 0, SMA50 < SMA200', low: -15, high: 0, unit: '%' },
    RSI(30, 48),
    { key: 'monthReturn', label: '1-month return', condition: '< 0%', low: -20, high: 0, unit: '%' },
  ],
  expansion: [
    { key: 'relativeVolume', label: 'Relative volume', condition: '≥ 1.5×', low: 1.5, high: 3.5, unit: '×' },
    { key: 'change', label: 'Day move', condition: '|2% – 10%|', low: -10, high: 10, unit: '%' },
  ],
};

export function ruleWindows(preset: Preset): RuleWindow[] {
  return RULE_WINDOWS[preset.id] ?? [];
}

/** Table columns: the windows that can be drawn and are not already context columns. */
export function ruleColumns(preset: Preset): RuleWindow[] {
  return ruleWindows(preset).filter((rule) => rule.low != null && rule.key !== 'change');
}

/** Position of a value inside its window, clamped to 0..1. `null` when undrawable. */
export function windowPosition(rule: RuleWindow, value: number | null): number | null {
  if (value == null || rule.low == null || rule.high == null || rule.high === rule.low) return null;
  return Math.max(0, Math.min(1, (value - rule.low) / (rule.high - rule.low)));
}

export function outsideWindow(rule: RuleWindow, value: number | null): boolean {
  return value != null && rule.low != null && rule.high != null && (value < rule.low || value > rule.high);
}

export function ruleValue(row: Candidate, rule: RuleWindow): number | null {
  const value = row[rule.key];
  return typeof value === 'number' ? value : null;
}

export function formatRuleValue(rule: RuleWindow, value: number | null): string {
  if (value == null) return '—';
  if (rule.unit === '×') return `${value.toFixed(2)}×`;
  if (rule.unit === '$') return compactMoney(value);
  if (rule.unit === '') return value.toFixed(1);
  // Widths are magnitudes; distances are signed.
  if (rule.key === 'bandWidth') return `${value.toFixed(1)}%`;
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
}

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  notation: 'compact',
  maximumFractionDigits: 1,
});
const compactMoney = (value: number) => money.format(value);
