import { useRef, useState } from 'react';
import { FileText, X } from 'lucide-react';
import { MarketFloatingPopover } from './MarketFloatingPopover';
import { MM } from './marketUi';

export type InsiderLookback = 'chart' | '90D' | '1Y' | '3Y' | '5Y' | 'MAX';
export type InsiderDisplayMode = 'individual' | 'clusters';

export function ChartEvidenceControl({
  showInsiderTransactions,
  onShowInsiderTransactions,
  lookback,
  onLookback,
  displayMode,
  onDisplayMode,
}: {
  showInsiderTransactions: boolean;
  onShowInsiderTransactions: (show: boolean) => void;
  lookback: InsiderLookback;
  onLookback: (lookback: InsiderLookback) => void;
  displayMode: InsiderDisplayMode;
  onDisplayMode: (mode: InsiderDisplayMode) => void;
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLButtonElement>(null);

  return (
    <div className="market-sec-control" style={{ position: 'relative', flex: '0 0 auto' }}>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-pressed={showInsiderTransactions}
        className="market-chart-tool-button"
        title="SEC chart events"
      >
        <FileText size={12} /> SEC{showInsiderTransactions ? ' · Form 4 on' : ''}
      </button>
      <MarketFloatingPopover anchorRef={triggerRef} open={open} onClose={() => setOpen(false)} className="market-sec-popover" width={340}>
        <div style={{ border: `1px solid ${MM.borderHi}`, borderRadius: 12, background: '#0b0b0d', padding: 13, boxShadow: '0 18px 36px rgba(0,0,0,.55)' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 12 }}>
            <div><div style={{ color: MM.text, font: '650 11px Inter' }}>SEC chart events</div><div style={{ marginTop: 3, color: MM.dim, fontSize: 10.5, lineHeight: 1.45 }}>8-K and Form 144 markers stay visible. Form 4 transactions are optional.</div></div>
            <button type="button" aria-label="Close SEC chart settings" onClick={() => setOpen(false)} className="chart-comparison-close"><X size={14} /></button>
          </div>
          <label className="market-sec-toggle">
            <span><b>Plot Form 4 transactions</b><small>Executed insider trades</small></span>
            <input type="checkbox" checked={showInsiderTransactions} onChange={(event) => onShowInsiderTransactions(event.target.checked)} />
          </label>
          <fieldset disabled={!showInsiderTransactions} className="market-sec-fieldset">
            <legend>Form 4 lookback</legend>
            <div className="market-sec-options">
              {(['chart', '90D', '1Y', '3Y', '5Y', 'MAX'] as const).map((value) => <button key={value} type="button" aria-pressed={lookback === value} onClick={() => onLookback(value)}>{value === 'chart' ? 'Chart range' : value === 'MAX' ? 'All' : value}</button>)}
            </div>
            <legend>Display</legend>
            <div className="market-sec-options">
              <button type="button" aria-pressed={displayMode === 'individual'} onClick={() => onDisplayMode('individual')}>Individual trades</button>
              <button type="button" aria-pressed={displayMode === 'clusters'} onClick={() => onDisplayMode('clusters')}>Cluster boxes</button>
            </div>
            <p>Cluster boxes summarize net flow by default. Individual mode is available when you want to inspect each executed trade.</p>
          </fieldset>
        </div>
      </MarketFloatingPopover>
    </div>
  );
}
