import { ArrowLeft, RefreshCw } from 'lucide-react';
import { MM } from './marketUi';

export function TickerLoadState({ symbol, error, onClose, onRetry }: { symbol: string; error: string | null; onClose: () => void; onRetry: () => Promise<void> }) {
  return (
    <div className="tw" style={{ display: 'grid', placeItems: 'center' }}>
      <div style={{ width: 'min(440px, 100%)', border: `1px solid ${error ? 'rgba(217,109,95,.3)' : MM.border}`, borderRadius: 6, background: MM.panel, padding: 22, textAlign: 'center' }}>
        <div style={{ color: error ? MM.down : MM.accent, font: '650 9px var(--mkt-sans)', letterSpacing: '.13em', textTransform: 'uppercase' }}>{error ? 'Asset unavailable' : 'Loading workspace'}</div>
        <h1 style={{ color: MM.text, margin: '11px 0 8px', fontFamily: 'var(--mkt-mono)', fontSize: 22 }}>{symbol}</h1>
        <p role={error ? 'alert' : undefined} style={{ color: MM.dim, fontSize: 11, lineHeight: 1.55 }}>{error ?? 'Loading price history, deterministic signals, and current evidence…'}</p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 15 }}>
          <button type="button" className="tw-btn" onClick={onClose}><ArrowLeft size={13} /> Market</button>
          {error && <button type="button" className="tw-btn" onClick={() => void onRetry()}><RefreshCw size={12} /> Retry</button>}
        </div>
      </div>
    </div>
  );
}
