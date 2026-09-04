import type { ViewResource } from '../chartAgent/types';
import type { FinancialChartRow, FinancialStory } from '../financialExplorer';
import type { EvidenceItem, FinancialFrequency, InsiderNetWindow, OverlaySeriesPayload } from '../types';

/** The chart/table rows are passed through unchanged; this adds their display semantics. */
export function financialPanelResource(input: {
  story: FinancialStory; frequency: FinancialFrequency; active: boolean; visibleMetrics: Set<string>;
  rows: FinancialChartRow[]; series: (OverlaySeriesPayload | null)[]; loading: boolean; errors: string[]; warnings: string[];
}): ViewResource {
  const { story, frequency, active, visibleMetrics, rows, series, loading, errors, warnings } = input;
  return { key: 'panel:fundamentals', kind: 'panel', label: 'Financial explorer',
    status: errors.length ? rows.length ? 'stale' : 'error' : loading && !rows.length ? 'not-loaded' : rows.length ? 'loaded' : 'empty',
    rows: rows.map((row) => ({ ...row })), metadata: { storyId: story.id, frequency, visibleMetrics: [...visibleMetrics],
      alignment: story.id === 'valuation' ? 'quarterly_last_price_timestamp' : 'period-end', timestampUnit: 'milliseconds',
      valueKind: story.valueKind, active,
      units: series.map((payload, index) => ({ metric: story.metrics[index]?.id, unit: payload?.observations[0]?.unit ?? null })),
      warnings, errors, sourceObservations: series.map((payload, index) => ({ metric: story.metrics[index]?.id, observations: payload?.observations ?? [] })) } };
}

export function evidencePanelResource(input: {
  visibleEvidence: EvidenceItem[]; selectedDay: string | null; insiderWindows: InsiderNetWindow[];
  depthDays: number; active: boolean; showMethod: boolean; loading: boolean;
  error: string | null; asOf?: string; warnings: string[];
}): ViewResource {
  const { visibleEvidence, selectedDay, insiderWindows, depthDays, active, showMethod, loading, error, asOf, warnings } = input;
  return { key: 'panel:evidence', kind: 'panel', label: 'SEC & Events',
    status: error ? visibleEvidence.length ? 'stale' : 'error' : loading && !visibleEvidence.length ? 'not-loaded' : visibleEvidence.length ? 'loaded' : 'empty',
    observedAt: asOf, rows: visibleEvidence.map((row) => ({ ...row })),
    metadata: { selectedDay, depthDays, active, timestampUnit: 'seconds', insiderWindows, warnings, showMethod } };
}
