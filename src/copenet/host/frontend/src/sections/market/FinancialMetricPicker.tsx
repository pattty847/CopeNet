import { Check, ChevronDown, Search } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { MarketFloatingPopover } from './MarketFloatingPopover';
import type { FinancialMetricInfo } from './types';

export function FinancialMetricPicker({
  metrics,
  selectedMetric,
  selectedLabel,
  loading,
  onMetric,
}: {
  metrics: FinancialMetricInfo[];
  selectedMetric: string | null;
  selectedLabel: string | null;
  loading: boolean;
  onMetric: (metric: string | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const triggerRef = useRef<HTMLButtonElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const filtered = metrics.filter((metric) => `${metric.label} ${metric.id}`.toLowerCase().includes(query.trim().toLowerCase()));

  const close = (restoreFocus: boolean) => {
    setOpen(false);
    setQuery('');
    if (restoreFocus) window.requestAnimationFrame(() => triggerRef.current?.focus());
  };

  useEffect(() => {
    if (!open) return;
    const frame = window.requestAnimationFrame(() => searchRef.current?.focus());
    return () => window.cancelAnimationFrame(frame);
  }, [open]);

  return (
    <div className="financial-metric-picker">
      <button
        ref={triggerRef}
        type="button"
        className={selectedMetric ? 'financial-metric-picker__trigger is-active' : 'financial-metric-picker__trigger'}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => open ? close(true) : setOpen(true)}
      >
        <span>{loading && selectedMetric ? 'Loading…' : selectedLabel ?? 'More…'}</span><ChevronDown size={11} aria-hidden="true" />
      </button>
      <MarketFloatingPopover anchorRef={triggerRef} open={open} onClose={() => close(true)} className="financial-metric-popover" width={330}>
        <div role="dialog" aria-label="Choose a financial chart overlay">
          <header><strong>Financial overlays</strong><span>Point-in-time SEC and valuation series</span></header>
          <label className="financial-metric-search"><Search size={13} aria-hidden="true" /><span className="sr-only">Search financial overlays</span><input ref={searchRef} type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search metrics" /></label>
          <div className="financial-metric-options">
            {filtered.length ? filtered.map((metric) => {
              const selected = metric.id === selectedMetric;
              return (
                <button key={metric.id} type="button" aria-pressed={selected} onClick={() => { onMetric(selected ? null : metric.id); close(true); }}>
                  <span><strong>{metric.label}</strong><small>{metric.factType === 'valuation' ? 'Price-backed valuation' : metric.derived ? 'Derived SEC series' : 'Reported SEC series'}</small></span>
                  {selected ? <Check size={13} aria-hidden="true" /> : null}
                </button>
              );
            }) : <p>No matching metrics.</p>}
          </div>
        </div>
      </MarketFloatingPopover>
    </div>
  );
}
