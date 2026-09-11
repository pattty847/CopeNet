// What a matched population looks like, so a screener tile and its definition say more
// than a count. Pure derivations over one screen's rows; nothing here fetches.
import type { Candidate } from './types';
import type { RuleWindow } from './ruleWindows';

export type ScreenSummary = {
  count: number;
  /** Matches as a share of the eligible universe, 0..1. */
  hitRate: number;
  sectors: { name: string; count: number }[];
  otherSectors: number;
  medians: Record<'change' | 'monthReturn' | 'relativeVolume' | 'dollarVolume' | 'marketCap', number | null> &
    Partial<Record<string, number | null>>;
};

export function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function medianOf(rows: Candidate[], key: keyof Candidate): number | null {
  return median(rows.map((row) => row[key]).filter((value): value is number => typeof value === 'number'));
}

const MEDIAN_KEYS: (keyof Candidate)[] = [
  'change',
  'monthReturn',
  'relativeVolume',
  'dollarVolume',
  'marketCap',
  'rsi',
  'drawdown',
  'bandWidth',
  'distance50',
  'distance200',
];

export function summarizeScreen(rows: Candidate[], eligible: number, leadingSectors = 5): ScreenSummary {
  const counts = new Map<string, number>();
  for (const row of rows) {
    const sector = row.sector || 'Sector unavailable';
    counts.set(sector, (counts.get(sector) ?? 0) + 1);
  }
  const sectors = [...counts.entries()]
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name));
  const medians = Object.fromEntries(MEDIAN_KEYS.map((key) => [key, medianOf(rows, key)])) as ScreenSummary['medians'];
  return {
    count: rows.length,
    hitRate: eligible > 0 ? rows.length / eligible : 0,
    sectors: sectors.slice(0, leadingSectors),
    otherSectors: sectors.slice(leadingSectors).reduce((sum, sector) => sum + sector.count, 0),
    medians,
  };
}

/** Bin counts of the ranking metric across its rule window, for the tile's distribution. */
export function metricHistogram(rows: Candidate[], rule: RuleWindow, bins = 12): number[] {
  const counts = new Array<number>(bins).fill(0);
  if (rule.low == null || rule.high == null || rule.high === rule.low) return counts;
  for (const row of rows) {
    const value = row[rule.key];
    if (typeof value !== 'number') continue;
    const position = Math.max(0, Math.min(0.999, (value - rule.low) / (rule.high - rule.low)));
    counts[Math.floor(position * bins)] += 1;
  }
  return counts;
}
