import { ExternalLink } from 'lucide-react';
import { formatFinancialDate } from './financialOverlay';
import {
  formatFinancialStoryValue,
  periodChange,
  type FinancialChartRow,
  type FinancialStory,
} from './financialExplorer';
import type { FinancialFrequency } from './types';

export function FinancialHistoryTable({
  rows,
  story,
  visibleMetrics,
  frequency,
  onToggleMetric,
}: {
  rows: FinancialChartRow[];
  story: FinancialStory;
  visibleMetrics: Set<string>;
  frequency: FinancialFrequency;
  onToggleMetric: (metricId: string) => void;
}) {
  const periods = rows.slice(-8);
  const periodStartIndex = Math.max(0, rows.length - periods.length);
  return (
    <div className="financial-history-wrap">
      <table className="financial-history-table">
        <caption className="sr-only">{story.label} history with filing sources and year-over-year changes</caption>
        <thead>
          <tr>
            <th scope="col">Metric</th>
            {periods.map((row) => <th key={row.key} scope="col">{row.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {story.metrics.map((metric) => {
            const visible = visibleMetrics.has(metric.id);
            return (
              <tr key={metric.id} data-visible={visible}>
                <th scope="row">
                  <button type="button" aria-pressed={visible} onClick={() => onToggleMetric(metric.id)}>
                    <i style={{ background: metric.color }} />
                    <span>{metric.label}</span>
                  </button>
                </th>
                {periods.map((row, localIndex) => {
                  const value = row[metric.id];
                  const meta = row._meta[metric.id];
                  const change = periodChange(rows, periodStartIndex + localIndex, metric.id, frequency);
                  return (
                    <td key={row.key}>
                      {typeof value === 'number' ? (
                        <>
                          <span>{formatFinancialStoryValue(value, story.valueKind)}</span>
                          {change == null ? <small>—</small> : <small>{change > 0 ? '+' : ''}{change.toFixed(1)}%</small>}
                          {meta?.source?.sourceUrl ? (
                            <a href={meta.source.sourceUrl} target="_blank" rel="noopener noreferrer" title={`Open ${meta.source.form} filed ${formatFinancialDate(meta.source.filed)}`} aria-label={`Open ${metric.label} source filing for ${row.label}`}>
                              {meta.source.form}<ExternalLink size={9} aria-hidden="true" />
                            </a>
                          ) : <em>{meta?.derived ? 'derived' : 'source unavailable'}</em>}
                        </>
                      ) : <span className="financial-history-empty">—</span>}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
