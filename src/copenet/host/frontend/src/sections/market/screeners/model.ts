import type { Candidate, ScreenerConfig } from './types';
export const DEFAULT_CONFIG: ScreenerConfig = {
  minCap: 10e9,
  maxCap: null,
  minPrice: 10,
  minDollarVolume: 25e6,
};
const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
  notation: 'compact',
  maximumFractionDigits: 1,
});
export const compactMoney = (value: number) => money.format(value);
export const decimal = (value: number | null, suffix = '') => (value == null ? '—' : `${value.toFixed(1)}${suffix}`);
export function metricValue(row: Candidate, metric: string): number | null {
  const value = row[metric as keyof Candidate];
  return typeof value === 'number' ? value : null;
}
export const METRIC_LABELS: Record<string, string> = {
  bandWidth: 'Band width',
  distance50: 'From SMA50',
  rsi: 'RSI',
  distance200: 'From SMA200',
  relativeVolume: 'Rel. volume',
};
export function sortCandidates(rows: Candidate[], metric: string, ascending: boolean): Candidate[] {
  return [...rows].sort((a, b) => {
    const left = metricValue(a, metric),
      right = metricValue(b, metric);
    if (left == null) return right == null ? a.id.localeCompare(b.id) : 1;
    if (right == null) return -1;
    return (ascending ? left - right : right - left) || a.id.localeCompare(b.id);
  });
}
export function downloadJson(payload: unknown, filename: string) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' }));
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export type ScreenerSelection = { runId: string; symbols: string[] };
export function loadSelection(): ScreenerSelection {
  try {
    const value = JSON.parse(sessionStorage.getItem('market-screener-selection') || 'null');
    if (
      value &&
      typeof value.runId === 'string' &&
      Array.isArray(value.symbols) &&
      value.symbols.every((symbol: unknown) => typeof symbol === 'string')
    )
      return value;
  } catch {
    /* Browser storage is optional. */
  }
  return { runId: '', symbols: [] };
}
export function saveSelection(value: ScreenerSelection) {
  try {
    sessionStorage.setItem('market-screener-selection', JSON.stringify(value));
  } catch {
    /* Optional preference. */
  }
}
export function loadPreset(): string {
  const routed = new URLSearchParams(window.location.search).get('screen');
  if (routed) return routed;
  try {
    return sessionStorage.getItem('market-screener-preset') || 'compression';
  } catch {
    return 'compression';
  }
}
export function savePreset(value: string) {
  try {
    sessionStorage.setItem('market-screener-preset', value);
  } catch {
    /* Optional preference. */
  }
}
