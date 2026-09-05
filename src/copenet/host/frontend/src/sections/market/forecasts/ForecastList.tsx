import { Eye, EyeOff } from 'lucide-react';
import { forecastDate, forecastRisk, forecastStatus, forecastTracking } from './model';
import type { ForecastRecord } from './types';

export function ForecastList({ records, onSelect, hidden, onToggle }: {
  records: ForecastRecord[]; onSelect: (id: string) => void; hidden?: ReadonlySet<string>; onToggle?: (id: string) => void;
}) {
  if (!records.length) return <p className="cf-empty">No forecasts yet. Choose “Forecast this chart” in the chart agent settings to record one.</p>;
  return <div className="cf-list">{records.map((record) => <div className="cf-row" key={record.forecastId}>
    <button className="cf-row-main" onClick={() => onSelect(record.forecastId)}>
      <span><strong>{record.instrument.symbol}</strong><small>{record.model} · {forecastDate(record.publishedAt ?? record.requestedAt)}</small></span>
      <span><strong>{forecastStatus(record)}</strong><small>Tracking {forecastTracking(record)} · {(record.evaluation?.health ?? 'unevaluated').replaceAll('_', ' ')}</small></span>
      <span><strong>{forecastRisk(record)}</strong><small>8w {record.evaluation?.horizons?.['8w']?.members.ta?.outcome ?? 'pending'}</small></span>
    </button>
    {onToggle && <button className="tw-iconbtn" aria-label={`${hidden?.has(record.forecastId) ? 'Show' : 'Hide'} ${record.instrument.symbol} forecast overlay`} aria-pressed={!hidden?.has(record.forecastId)} onClick={() => onToggle(record.forecastId)}>
      {hidden?.has(record.forecastId) ? <EyeOff size={15} /> : <Eye size={15} />}</button>}
  </div>)}</div>;
}
