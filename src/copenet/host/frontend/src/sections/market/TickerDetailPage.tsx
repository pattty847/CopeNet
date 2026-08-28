import { ArrowLeft, RefreshCw } from 'lucide-react';
import { useState } from 'react';
import { useAppStore } from '../../store/useAppStore';
import { MM, toneColor } from './marketUi';
import { TickerAssetSwitcher } from './TickerAssetSwitcher';
import { TickerChartWorkspace } from './TickerChartWorkspace';
import { TickerContextStrip, type TickerResearchTab } from './TickerContextStrip';
import { TickerResearchDock } from './TickerResearchDock';
import { useTickerDetail, useTickerEvidence, type MarketWatchlistState } from './useMarketMonitorData';

function formatQuote(value?: number | null): string {
  return value == null ? '—' : value.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function formatBarDate(value?: number | null): string {
  if (!value) return 'bar date unavailable';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value * 1000));
}

export function TickerDetailPage({
  symbol,
  onClose,
  onOpenTicker,
  watchlist,
}: {
  symbol: string;
  onClose: () => void;
  onOpenTicker: (symbol: string) => void;
  watchlist: MarketWatchlistState;
}) {
  const ticker = useTickerDetail(symbol);
  const sec = useTickerEvidence(symbol);
  const setCommandPaletteOpen = useAppStore((state) => state.setCommandPaletteOpen);
  const [watchBusy, setWatchBusy] = useState(false);
  const [researchTab, setResearchTab] = useState<TickerResearchTab>('overview');

  if (ticker.loading || !ticker.detail) {
    return <TickerLoadState symbol={symbol} error={ticker.error} onClose={onClose} onRetry={ticker.reload} />;
  }

  const detail = ticker.detail;
  const isWatched = watchlist.symbols.has(detail.symbol);
  const toggleWatch = async () => {
    setWatchBusy(true);
    try {
      if (isWatched) await watchlist.remove(detail.symbol);
      else await watchlist.add(detail.symbol, detail.name);
    } finally {
      setWatchBusy(false);
    }
  };
  const change = detail.quote.changePct;
  const quoteTone = change == null || change === 0 ? 'flat' : change > 0 ? 'up' : 'down';
  const chartEvents = sec.payload?.events ?? detail.events;
  const evidence = sec.payload?.evidence?.length ? sec.payload.evidence : detail.evidence;
  const displayName = detail.name.trim().toUpperCase() === detail.symbol.trim().toUpperCase() ? '' : detail.name;

  return (
    <div className="market-ticker-detail ticker-workspace">
      <header className="ticker-workspace-header">
        <div className="ticker-identity-group">
          <button type="button" onClick={onClose} className="ticker-back-button"><ArrowLeft size={14} /> Market</button>
          <div className="ticker-identity-copy">
            <div className="ticker-identity-title"><h1>{detail.symbol}</h1>{displayName && <span>{displayName}</span>}</div>
            <div className="ticker-identity-meta">Latest daily bar · {formatBarDate(detail.quote.barTime)} · {detail.quote.priceBasis.replace('_', '-')}</div>
          </div>
        </div>
        <div className="ticker-header-actions">
          <div className="ticker-quote"><strong>{formatQuote(detail.quote.price)}</strong><span style={{ color: toneColor(quoteTone) }}>{change == null ? '—' : `${change > 0 ? '+' : ''}${change.toFixed(2)}%`} vs prior daily bar</span></div>
          <TickerAssetSwitcher currentSymbol={detail.symbol} items={watchlist.items} onSearch={() => setCommandPaletteOpen(true)} onSelect={onOpenTicker} />
          <button type="button" onClick={() => void toggleWatch()} disabled={watchBusy} className={isWatched ? 'ticker-watch-button is-active' : 'ticker-watch-button'}>{watchBusy ? 'Updating…' : isWatched ? '✓ Watching' : '+ Watch'}</button>
        </div>
      </header>

      <main className="ticker-workspace-main">
        <TickerChartWorkspace detail={detail} events={chartEvents} evidence={evidence} />
        <TickerContextStrip detail={detail} evidence={evidence} onOpenTab={setResearchTab} />
        <TickerResearchDock activeTab={researchTab} detail={detail} evidence={evidence} evidenceState={sec} onTab={setResearchTab} />
      </main>
    </div>
  );
}

function TickerLoadState({ symbol, error, onClose, onRetry }: { symbol: string; error: string | null; onClose: () => void; onRetry: () => Promise<void> }) {
  return (
    <div className="market-ticker-detail" style={{ display: 'grid', minHeight: 440, placeItems: 'center' }}>
      <div style={{ width: 'min(480px, 100%)', border: `1px solid ${error ? 'rgba(217,109,95,.35)' : MM.border}`, borderRadius: 6, background: MM.panel, padding: 22, textAlign: 'center' }}>
        <div style={{ color: error ? MM.down : MM.accent, font: '650 10px Inter', letterSpacing: '.12em', textTransform: 'uppercase' }}>{error ? 'Asset unavailable' : 'Loading asset workspace'}</div>
        <h1 style={{ color: MM.text, margin: '12px 0 8px', fontFamily: "'JetBrains Mono', monospace" }}>{symbol.toUpperCase()}</h1>
        <p role={error ? 'alert' : undefined} style={{ color: MM.dim, fontSize: 12, lineHeight: 1.55 }}>{error ?? 'Loading price history, deterministic signals, portfolio context, and current evidence…'}</p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 15 }}><button type="button" onClick={onClose} className="ticker-back-button"><ArrowLeft size={14} /> Market</button>{error && <button type="button" onClick={() => void onRetry()} className="ticker-watch-button"><RefreshCw size={13} /> Retry</button>}</div>
      </div>
    </div>
  );
}
