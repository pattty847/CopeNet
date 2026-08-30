import { useMemo, useState } from 'react';
import { ChevronDown, Search } from 'lucide-react';
import type { FinancialMetricInfo } from './types';

const GROUPS: { key: FinancialMetricInfo['factType']; label: string }[] = [
  { key: 'duration', label: 'Income & cash flow' },
  { key: 'instant', label: 'Balance sheet' },
  { key: 'derived', label: 'Derived' },
  { key: 'valuation', label: 'Valuation' },
];

function frequencyLabel(metric: FinancialMetricInfo): string {
  if (metric.factType === 'valuation') return 'TTM';
  return metric.frequencies
    ?.map((value) => value === 'quarterly' ? 'Q' : value === 'annual' ? 'A' : 'TTM')
    .join(' · ') ?? 'Q · TTM · A';
}

export function FinancialSeriesPicker({
  metrics,
  selectedMetric,
  disabled,
  onSelect,
}: {
  metrics: FinancialMetricInfo[];
  selectedMetric: string | null;
  disabled: boolean;
  onSelect: (metric: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [query, setQuery] = useState('');
  const selected = metrics.find((metric) => metric.id === selectedMetric);
  const grouped = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    const visible = normalized
      ? metrics.filter((metric) => `${metric.label} ${metric.id}`.toLowerCase().includes(normalized))
      : metrics;
    return GROUPS.map((group) => ({
      ...group,
      metrics: visible.filter((metric) => metric.factType === group.key),
    })).filter((group) => group.metrics.length > 0);
  }, [metrics, query]);

  return (
    <div className="tw-series-picker">
      <button
        type="button"
        className="tw-plotrow"
        aria-expanded={expanded}
        disabled={disabled}
        onClick={() => setExpanded((value) => !value)}
      >
        Financial series
        <span className="tw-plotrow__val">{selected?.label ?? 'Choose'} <ChevronDown size={12} data-open={expanded} /></span>
      </button>

      {expanded && !disabled && (
        <div className="tw-series-picker__menu">
          <label className="tw-series-picker__search">
            <Search size={12} aria-hidden="true" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search financials"
              aria-label="Search financial series"
              autoFocus
            />
          </label>
          <div className="tw-series-picker__list">
            {grouped.map((group) => (
              <div key={group.key} className="tw-series-picker__group">
                <div className="tw-series-picker__group-label">{group.label}</div>
                {group.metrics.map((metric) => (
                  <button
                    key={metric.id}
                    type="button"
                    className="tw-series-picker__option"
                    aria-pressed={metric.id === selectedMetric}
                    onClick={() => onSelect(metric.id)}
                  >
                    <span>{metric.label}</span>
                    <small>{frequencyLabel(metric)}</small>
                  </button>
                ))}
              </div>
            ))}
            {grouped.length === 0 && <div className="tw-series-picker__empty">No matching series</div>}
          </div>
        </div>
      )}
    </div>
  );
}
