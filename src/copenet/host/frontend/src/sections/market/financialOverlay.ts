import type { FinancialSeriesObservation } from './types';

export interface FinancialOverlayPoint {
  t: number;
  value: number | null;
}

export interface FinancialOverlayValuePoint {
  t: number;
  value: number;
}

export function hasRenderableFinancialOverlay(
  points: FinancialOverlayPoint[] | undefined,
): boolean {
  return points?.some(
    (point) => Number.isFinite(point.t) && point.value != null && Number.isFinite(point.value),
  ) ?? false;
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

/** Move every overlay point onto a real candle timestamp.
 *
 *  Lightweight Charts' time axis is INDEX-based: every unique timestamp across every
 *  attached series takes one equal-width slot, regardless of how far apart two of them
 *  actually are. So an overlay point landing on its filing date — a Thursday, against
 *  weekly candles anchored to Mondays — does not sit between two bars, it *inserts a new
 *  bar-width slot* between them. Seventy filings inject seventy slots, which compresses
 *  the candles and corrupts the `barSpacing` the SEC cluster boxes size themselves from.
 *
 *  Snapping is FORWARD only: a filing becomes visible on the first candle at or after it
 *  became public, never earlier. Snapping backward would render a filing before it
 *  existed, which is the same lookahead that aligning to `availableAt` exists to prevent.
 *
 *  Points with no candle at or after them are dropped rather than clamped to the last
 *  bar — a future-dated point pinned to the right edge reads as real, current data.
 *  Points before the first candle are likewise dropped: clamping them forward would pile
 *  every pre-chart filing onto bar one.
 */
export function snapOverlayToCandles(
  points: FinancialOverlayPoint[],
  candleTimes: number[],
): FinancialOverlayPoint[] {
  if (!points.length || !candleTimes.length) return [];
  const times = [...new Set(candleTimes.filter((t) => Number.isFinite(t)))].sort((a, z) => a - z);
  if (!times.length) return [];
  const firstTime = times[0];
  const lastTime = times[times.length - 1];
  const snapped: FinancialOverlayPoint[] = [];
  for (const point of points) {
    if (!Number.isFinite(point.t) || point.t < firstTime || point.t > lastTime) continue;
    // Binary search for the first candle at or after this point.
    let low = 0;
    let high = times.length - 1;
    while (low < high) {
      const mid = (low + high) >> 1;
      if (times[mid] < point.t) low = mid + 1;
      else high = mid;
    }
    snapped.push({ t: times[low], value: point.value });
  }
  return snapped;
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
  // Dimensionless series (margins, intensities) read as percentages;
  // coverage-style multiples carry unit "x" and read as 29.1×.
  if (unit === 'ratio') return `${(value * 100).toFixed(1)}%`;
  if (unit === 'x') return `${value.toFixed(1)}×`;
  if (unit === 'shares') {
    if (magnitude >= 1e9) return `${(value / 1e9).toFixed(2)}B sh`;
    if (magnitude >= 1e6) return `${(value / 1e6).toFixed(0)}M sh`;
    return `${Math.round(value).toLocaleString()} sh`;
  }
  const prefix = unit === 'USD' ? '$' : `${unit} `;
  if (magnitude >= 1e12) return `${prefix}${(value / 1e12).toFixed(2)}T`;
  if (magnitude >= 1e9) return `${prefix}${(value / 1e9).toFixed(2)}B`;
  if (magnitude >= 1e6) return `${prefix}${(value / 1e6).toFixed(0)}M`;
  return `${prefix}${Math.round(value).toLocaleString()}`;
}

/** Axis formatter for the overlay's left price scale. Valuation multiples read as
 *  "24.3×", inverted valuations (yields) as percentages; everything else follows
 *  the unit the observations carry. */
export function overlayAxisFormatter(
  unit: string | undefined,
  valuation: boolean,
  inverted = false,
): (value: number) => string {
  if (valuation && inverted) return (value: number) => `${(value * 100).toFixed(1)}%`;
  if (valuation) return (value: number) => `${value.toFixed(1)}×`;
  return (value: number) => formatFinancialValue(value, unit ?? 'USD');
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
