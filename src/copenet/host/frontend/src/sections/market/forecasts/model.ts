import { forecastSetup, type ForecastRecord } from './types';

export function forecastStatus(record: ForecastRecord): string {
  return (record.status === 'published' ? record.evaluation?.state ?? 'waiting_entry' : record.status).replaceAll('_', ' ');
}
export function forecastRisk(record: ForecastRecord): string {
  const value = record.evaluation?.plannedRiskR;
  return value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}R`;
}
export function forecastDate(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit' }) : 'Pending';
}

/** Levels use the chart's confirmed split basis, never guessed from ticker identity. */
export function forecastDisplay(record: ForecastRecord, splitFingerprint?: string): { factor: number; reason?: string } {
  const source = record.evaluation?.source;
  const expected = source?.splitFingerprint ?? record.provenance?.splitFingerprint;
  if (typeof splitFingerprint !== 'string' || expected !== splitFingerprint) return { factor: 1, reason: 'Chart and forecast price bases do not match. Refresh the chart or inspect the revision notice.' };
  const factor = source?.publicationBasisFactor ?? 1;
  if (!Number.isFinite(factor) || factor <= 0) return { factor: 1, reason: 'Forecast price basis is unavailable.' };
  if (record.evaluation?.health === 'revision_review') return { factor, reason: 'Price history revision needs review.' };
  return { factor };
}

export function forecastLevels(record: ForecastRecord, factor = 1) {
  const setup = forecastSetup(record);
  if (!setup) return [];
  return [
    { id: 'entry', price: setup.entry.price / factor, label: `${setup.entry.kind === 'limit' ? 'Limit' : 'Stop'} entry`, color: '#fb9423' },
    { id: 'stop', price: setup.stop / factor, label: 'Stop loss', color: '#e46b66' },
    ...setup.targets.map((target, index) => ({ id: `target-${index}`, price: target.price / factor, label: `TP${index + 1} · ${Math.round(target.fraction * 100)}%`, color: '#78bd91' })),
  ];
}

export function forecastTracking(record: ForecastRecord): string {
  return (record.tracking?.status ?? (record.trackingScanId ? 'unavailable' : 'paused')).replaceAll('_', ' ');
}

export function forecastThesis(record: ForecastRecord): string {
  if (record.members.ta?.result?.thesis) return record.members.ta.result.thesis;
  if (record.status === 'requested' || record.status === 'generating') return 'Generating from your frozen chart evidence…';
  if (record.status === 'cancelled') return 'Request cancelled. No TA setup was published.';
  if (record.status === 'failed') return 'The TA request failed. Its attempt and any available lane results are retained below.';
  if (record.status === 'no_setup') return 'No TA setup was returned.';
  return 'The TA result is unavailable. Inspect the recorded lane status below.';
}
