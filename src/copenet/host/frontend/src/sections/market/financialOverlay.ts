import type { FinancialSeriesObservation } from './types';

export interface FinancialOverlayPoint {
  t: number;
  value: number | null;
}

export interface FinancialOverlayValuePoint {
  t: number;
  value: number;
}

export function splitFinancialOverlaySegments(
  points: FinancialOverlayPoint[],
): FinancialOverlayValuePoint[][] {
  const byTime = new Map<number, FinancialOverlayPoint>();
  for (const point of points) {
    if (
      Number.isFinite(point.t)
      && (point.value == null || Number.isFinite(point.value))
    ) byTime.set(point.t, point);
  }
  const ordered = [...byTime.values()].sort((left, right) => left.t - right.t);
  const segments: FinancialOverlayValuePoint[][] = [];
  let segment: FinancialOverlayValuePoint[] = [];
  for (const point of ordered) {
    if (point.value == null) {
      if (segment.length) segments.push(segment);
      segment = [];
      continue;
    }
    segment.push({ t: point.t, value: point.value });
  }
  if (segment.length) segments.push(segment);
  return segments;
}

export function observationTime(observation: FinancialSeriesObservation): number {
  return Math.floor(Date.parse(`${observation.availableAt}T00:00:00Z`) / 1000);
}

export function formatFinancialValue(value: number, unit: string = 'USD'): string {
  const magnitude = Math.abs(value);
  if (unit === 'USD/shares') {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 3,
    }).format(value);
  }
  const prefix = unit === 'USD' ? '$' : `${unit} `;
  if (magnitude >= 1e12) return `${prefix}${(value / 1e12).toFixed(2)}T`;
  if (magnitude >= 1e9) return `${prefix}${(value / 1e9).toFixed(2)}B`;
  if (magnitude >= 1e6) return `${prefix}${(value / 1e6).toFixed(0)}M`;
  return `${prefix}${Math.round(value).toLocaleString()}`;
}

export function formatFinancialDate(value: string): string {
  const parsed = new Date(`${value}T00:00:00Z`);
  return new Intl.DateTimeFormat(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  }).format(parsed);
}
