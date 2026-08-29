import type { EvidenceItem } from './types';

export type SecActivityUnit = 'money' | 'shares';

export interface SecActivityRow {
  day: string;
  label: string;
  timestamp: number;
  executedValue: number;
  plannedValue: number;
  executedPercentile: number | null;
  plannedPercentile: number | null;
  buys: number;
  sells: number;
  neutral: number;
  plannedSales: number;
  entries: EvidenceItem[];
}

export function evidenceDay(item: EvidenceItem): string | null {
  if (item.t == null) return null;
  return new Date(item.t * 1000).toISOString().slice(0, 10);
}

function signedAmount(item: EvidenceItem, unit: SecActivityUnit): number | null {
  const amount = unit === 'money' ? item.value : item.shares;
  if (amount == null || !Number.isFinite(amount) || amount === 0) return null;
  if (item.tone === 'down') return -Math.abs(amount);
  if (item.tone === 'up') return Math.abs(amount);
  return 0;
}

function percentile(magnitudes: number[], value: number): number | null {
  if (!value || magnitudes.length === 0) return null;
  return Math.round((magnitudes.filter((candidate) => candidate <= Math.abs(value)).length / magnitudes.length) * 100);
}

export function buildSecActivityRows(evidence: EvidenceItem[], unit: SecActivityUnit): SecActivityRow[] {
  const grouped = new Map<string, Omit<SecActivityRow, 'executedPercentile' | 'plannedPercentile'>>();
  evidence.forEach((item) => {
    if (item.type !== 'Insider' && item.type !== 'Form 144') return;
    if (item.flag === 'cluster') return;
    const day = evidenceDay(item);
    const amount = signedAmount(item, unit);
    if (!day || amount == null) return;
    const date = new Date(`${day}T00:00:00Z`);
    const current = grouped.get(day) ?? {
      day,
      label: new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric' }).format(date),
      timestamp: date.getTime(),
      executedValue: 0,
      plannedValue: 0,
      buys: 0,
      sells: 0,
      neutral: 0,
      plannedSales: 0,
      entries: [],
    };
    if (item.type === 'Form 144') {
      current.plannedValue -= Math.abs(amount);
      current.plannedSales += 1;
    } else {
      current.executedValue += amount;
      if (item.tone === 'up') current.buys += 1;
      else if (item.tone === 'down') current.sells += 1;
      else current.neutral += 1;
    }
    current.entries.push(item);
    grouped.set(day, current);
  });
  const ordered = [...grouped.values()].sort((a, b) => a.timestamp - b.timestamp);
  const executedMagnitudes = ordered.map((row) => Math.abs(row.executedValue)).filter(Boolean).sort((a, b) => a - b);
  const plannedMagnitudes = ordered.map((row) => Math.abs(row.plannedValue)).filter(Boolean).sort((a, b) => a - b);
  return ordered.map((row) => ({
    ...row,
    executedPercentile: percentile(executedMagnitudes, row.executedValue),
    plannedPercentile: percentile(plannedMagnitudes, row.plannedValue),
  }));
}

export function formatSecActivityValue(value: number, unit: SecActivityUnit): string {
  const formatter = new Intl.NumberFormat(undefined, { notation: 'compact', maximumFractionDigits: 1 });
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  const amount = formatter.format(Math.abs(value));
  return unit === 'money' ? `${sign}$${amount}` : `${sign}${amount} sh`;
}
