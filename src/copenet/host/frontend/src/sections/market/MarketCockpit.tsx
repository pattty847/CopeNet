// The market cockpit frame — the market-level twin of the ticker workspace.
//
// One fixed frame, no page scroll. The bar orients (regime, freshness, VIX/breadth), the
// watch rail navigates, the stage answers "what changed / what is standing", and the
// research dock beneath holds every deeper mode on a resizable seam. Hierarchy:
// Market → Delta → Standing tape → Investigation → Synthesis.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { RefreshCw, Search } from 'lucide-react';
import { wsClient } from '../../lib/wsClient';
import { BriefColumn } from './BriefColumn';
import { BriefingReasoning } from './BriefingReasoning';
import {
  loadCockpitRailCollapsed,
  saveCockpitRailCollapsed,
  type MarketDockTab,
} from './marketCockpitState';
import { MarketDock } from './MarketDock';
import { SymbolJump } from './SymbolJump';
import { TapeColumn } from './TapeColumn';
import { buildCockpitRail, WatchRail } from './WatchRail';
import { useMarketDockLayout } from './useMarketDockLayout';
import { useEconomicCalendar } from './useEconomicCalendar';
import { EconomicCalendarWidget } from './EconomicCalendarWidget';
import {
  useForwardLedger,
  useMarketDashboard,
  useMarketRead,
  useMarketSessions,
  useMorningBrief,
  useTradeLedger,
  type MarketWatchlistState,
} from './useMarketMonitorData';
import './tickerWorkspace.css';
import './marketCockpit.css';

const REGIME_LABELS: Record<string, string> = {
  'risk-off': 'Risk-off',
  chop: 'Chop',
  'risk-on': 'Risk-on',
  'event-risk': 'Event-risk',
};

const REGIME_COLORS: Record<string, string> = {
  'risk-off': 'var(--mkt-down)',
  chop: 'var(--mkt-muted)',
  'risk-on': 'var(--mkt-up)',
  'event-risk': 'var(--mkt-accent)',
};

export function MarketCockpit({
  onOpenTicker,
  watchlist,
}: {
  onOpenTicker: (symbol: string, type?: 'symbol' | 'formula') => void;
  watchlist: MarketWatchlistState;
}) {
  const { dashboard: dash, refreshing, live, refresh, reload } = useMarketDashboard();
  const { read, running: reading, error: readError, run: runRead } = useMarketRead();
  const marketSessions = useMarketSessions();
  const morningBrief = useMorningBrief(reload);
  const economicCalendar = useEconomicCalendar();
  const forwardLedger = useForwardLedger();
  const tradeLedger = useTradeLedger();
  const dock = useMarketDockLayout();

  const [railCollapsed, setRailCollapsed] = useState(loadCockpitRailCollapsed);
  const [railCursor, setRailCursor] = useState<string | null>(null);
  const [jumpOpen, setJumpOpen] = useState(false);
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [webullSyncing, setWebullSyncing] = useState(false);

  useEffect(() => saveCockpitRailCollapsed(railCollapsed), [railCollapsed]);

  const open = useCallback((symbol: string) => onOpenTicker(symbol, 'symbol'), [onOpenTicker]);

  const railEntries = useMemo(
    () => buildCockpitRail(watchlist, morningBrief.brief?.movers ?? []),
    [watchlist, morningBrief.brief],
  );

  const syncWebull = useCallback(async () => {
    setWebullSyncing(true);
    try {
      await wsClient.marketWebullSync();
      // The broker sync runs server-side; re-pull the stored dashboard until it lands.
      for (let attempt = 0; attempt < 8; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 5000));
        await reload();
      }
    } catch {
      // The dashboard refresh will expose the last healthy broker state.
    } finally {
      setWebullSyncing(false);
    }
  }, [reload]);

  // ------------------------------------------------------------------ keyboard
  const jumpOpenRef = useRef(jumpOpen);
  jumpOpenRef.current = jumpOpen;
  const railEntriesRef = useRef(railEntries);
  railEntriesRef.current = railEntries;
  const railCursorRef = useRef(railCursor);
  railCursorRef.current = railCursor;

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const owned = Boolean(
        target
          && (target.tagName === 'INPUT'
            || target.tagName === 'TEXTAREA'
            || target.tagName === 'SELECT'
            || target.tagName === 'BUTTON'
            || target.tagName === 'A'
            || target.isContentEditable
            || target.closest('[role="dialog"]')),
      );
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (owned || jumpOpenRef.current) return;

      const key = event.key;
      if (key === '/') {
        setJumpOpen(true);
        event.preventDefault();
        return;
      }
      if (key === '\\') {
        dock.cycleSnap();
        event.preventDefault();
        return;
      }
      if (key === 'j' || key === 'k') {
        const entries = railEntriesRef.current;
        if (!entries.length) return;
        const symbols = entries.map((entry) => entry.symbol);
        const from = railCursorRef.current;
        const at = from ? symbols.indexOf(from) : -1;
        const next = key === 'j'
          ? symbols[Math.min(at + 1, symbols.length - 1)]
          : symbols[Math.max(at - 1, 0)];
        if (next) {
          setRailCursor(next);
          event.preventDefault();
        }
        return;
      }
      if (key === 'Enter' && railCursorRef.current) {
        open(railCursorRef.current);
        event.preventDefault();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [dock, open]);

  const briefing = dash.briefing.data;
  const activeRegime = read?.regime ?? dash.regime.data.current;
  const ledgerLine = forwardLedger.report && forwardLedger.report.totalClaims > 0
    ? `${forwardLedger.report.totalClaims} claims logged · ${forwardLedger.report.pendingHorizons} horizons pending`
    : null;

  const openDock = useCallback((tab: MarketDockTab) => dock.openTab(tab), [dock]);

  return (
    <div className="mc">
      <header className="mc-bar">
        <div className="mc-bar__identity">
          <h1 className="mc-bar__title">MARKET</h1>
          <span className="mc-bar__name">slow-timeframe radar</span>
        </div>

        <span className="mc-regime" style={{ color: REGIME_COLORS[activeRegime] ?? 'var(--mkt-soft)' }} title={read?.regimeReasoning || 'Current regime read'}>
          <span className="mc-regime__dot" style={{ background: 'currentColor' }} />
          {REGIME_LABELS[activeRegime] ?? activeRegime}
        </span>

        <span className="mc-freshness" role="status">
          <span className="mc-freshness__dot" style={{ background: live ? 'var(--mkt-up)' : 'var(--mkt-dim)' }} />
          {live ? dash.asOf : 'illustrative preview'}
        </span>

        <div className="mc-bar__spacer" />

        <div className="mc-bar__stat" title="CBOE Volatility Index">
          <b>{Number.isFinite(briefing.vix) ? briefing.vix.toFixed(1) : '—'}</b>
          <span>VIX</span>
        </div>
        <div className="mc-bar__stat" title="Share of tracked names above their 50-week average">
          <b>{Number.isFinite(briefing.breadthPct) ? `${Math.round(briefing.breadthPct)}%` : '—'}</b>
          <span>Breadth</span>
        </div>

        <span className="tw-sep" />

        <button type="button" className="tw-btn" onClick={() => void refresh()} disabled={refreshing} data-active={refreshing || undefined}>
          <RefreshCw size={12} className={refreshing ? 'tw-spin' : undefined} />
          {refreshing ? 'Refreshing…' : 'Refresh data'}
        </button>
        <button type="button" className="tw-iconbtn" onClick={() => setJumpOpen(true)} title="Jump to symbol ( / )" aria-label="Jump to symbol">
          <Search size={14} />
        </button>
      </header>

      <div className="mc-body">
        <WatchRail
          watchlist={watchlist}
          entries={railEntries}
          cursor={railCursor}
          collapsed={railCollapsed}
          onToggle={() => setRailCollapsed((value) => !value)}
          onSelect={open}
        />

        <div className="mc-main">
          <div className="mc-stage">
            <BriefColumn
              brief={morningBrief.brief}
              generating={morningBrief.generating}
              onRunNow={() => void morningBrief.runNow()}
              regime={dash.regime}
              regimeReasoningAvailable
              read={read}
              reading={reading}
              readError={readError}
              onRunRead={() => void runRead()}
              onExplain={() => setReasoningOpen(true)}
              onOpen={open}
              calendar={
                <EconomicCalendarWidget
                  calendar={economicCalendar.calendar}
                  loading={economicCalendar.loading}
                  refreshing={economicCalendar.refreshing}
                  error={economicCalendar.error}
                  onRefresh={() => void economicCalendar.refresh()}
                />
              }
              ledgerLine={ledgerLine}
              onOpenLedger={() => openDock('ledger')}
            />
            <TapeColumn dash={dash} onOpen={open} openDock={openDock} />
          </div>

          <MarketDock
            tab={dock.tab}
            onTab={dock.openTab}
            snap={dock.snap}
            onSnap={dock.setSnap}
            size={dock.size}
            onResize={dock.resize}
            onCycleSnap={dock.cycleSnap}
            dash={dash}
            read={read}
            onOpen={open}
            tradeLedger={tradeLedger}
            ledger={forwardLedger.report}
            ledgerLoading={forwardLedger.loading}
            onSyncWebull={() => void syncWebull()}
            webullSyncing={webullSyncing}
          />

          {jumpOpen && (
            <SymbolJump
              seed=""
              onClose={() => setJumpOpen(false)}
              onPick={(picked, type) => {
                setJumpOpen(false);
                onOpenTicker(picked, type);
              }}
            />
          )}
        </div>
      </div>

      {reasoningOpen && (
        <BriefingReasoning dash={dash} read={read} sessions={marketSessions} onClose={() => setReasoningOpen(false)} />
      )}
    </div>
  );
}
