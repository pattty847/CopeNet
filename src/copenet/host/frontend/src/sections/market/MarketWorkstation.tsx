// The market workstation — the broad-market mode of the same instrument as the ticker
// workspace.
//
// Fixed chrome (market bar, watch rail, section tabs) around one scrolling section body.
// Briefing is home; Structure, Signals, Portfolio, Evidence, Ledger and Backtest are places
// you go and stay, each with the whole body. Nothing is split: the ticker page keeps its
// research dock because the chart must stay visible while you read about it; this page has
// no such anchor. The section is a route (`?view=`) owned by MarketMonitor; this component
// only asks for a change.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { MarketSection } from '../../lib/appSectionRouting';
import { useIsMobile, useViewportWidth } from '../../lib/responsive';
import { wsClient } from '../../lib/wsClient';
import { BriefingReasoning } from './BriefingReasoning';
import { buildWorkstationRail, stepSymbols } from './marketBriefModel';
import {
  MARKET_SECTION_TABS,
  RAIL_HIDDEN_PX,
  WATCHLIST_TAB,
  loadDensity,
  loadRailPreference,
  loadSectionVisits,
  railCollapsed,
  saveDensity,
  saveRailPreference,
  saveSectionVisits,
  sectionNewCounts,
  type SectionVisits,
} from './marketWorkstationState';
import { SymbolJump } from './SymbolJump';
import { useEconomicCalendar } from './useEconomicCalendar';
import {
  useForwardLedger,
  useMarketDashboard,
  useMarketRead,
  useMarketSessions,
  useMorningBrief,
  useTradeLedger,
  type MarketWatchlistState,
} from './useMarketMonitorData';
import { BacktestSection } from './workstation/BacktestSection';
import { BriefingSection } from './workstation/BriefingSection';
import { EvidenceSection } from './workstation/EvidenceSection';
import { LedgerSection } from './workstation/LedgerSection';
import { MarketBar } from './workstation/MarketBar';
import { MarketSectionTabs } from './workstation/MarketSectionTabs';
import { PortfolioSection } from './workstation/PortfolioSection';
import { SignalsSection } from './workstation/SignalsSection';
import { StructureSection } from './workstation/StructureSection';
import { WatchRail } from './workstation/WatchRail';
import './tickerWorkspace.css';
import './marketWorkstation.css';

export function MarketWorkstation({
  section,
  onSelectSection,
  onOpenTicker,
  watchlist,
}: {
  section: MarketSection;
  onSelectSection: (section: MarketSection) => void;
  onOpenTicker: (symbol: string, type?: 'symbol' | 'formula') => void;
  watchlist: MarketWatchlistState;
}) {
  const { dashboard, refreshing, live, refresh, reload } = useMarketDashboard();
  const { read, running: reading, error: readError, run: runRead } = useMarketRead();
  const marketSessions = useMarketSessions();
  const morningBrief = useMorningBrief(reload);
  const economicCalendar = useEconomicCalendar();
  const forwardLedger = useForwardLedger();
  const tradeLedger = useTradeLedger();

  const viewportWidth = useViewportWidth();
  const isMobile = useIsMobile();
  const railHidden = viewportWidth < RAIL_HIDDEN_PX;

  const [railPreference, setRailPreference] = useState(loadRailPreference);
  const [density, setDensity] = useState(loadDensity);
  const [visits, setVisits] = useState<SectionVisits>(loadSectionVisits);
  const [railCursor, setRailCursor] = useState<string | null>(null);
  const [jumpOpen, setJumpOpen] = useState(false);
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [webullSyncing, setWebullSyncing] = useState(false);

  const collapsed = railCollapsed(railPreference, viewportWidth);
  const tabs = railHidden ? [WATCHLIST_TAB, ...MARKET_SECTION_TABS] : MARKET_SECTION_TABS;
  // The watchlist tab only exists while the rail is hidden; on a wide screen it is the rail.
  const active: MarketSection = section === 'watchlist' && !railHidden ? 'briefing' : section;

  useEffect(() => saveDensity(density), [density]);

  // Opening a section clears its "new" count: the tab strip is an inbox.
  useEffect(() => {
    if (active === 'watchlist') return;
    setVisits((current) => {
      const next = { ...current, [active]: new Date().toISOString() };
      saveSectionVisits(next);
      return next;
    });
  }, [active, morningBrief.brief?.generatedAt]);

  const newCounts = useMemo(() => {
    const counts = sectionNewCounts(morningBrief.brief, visits);
    delete counts[active];
    return counts;
  }, [active, morningBrief.brief, visits]);
  const warnings = useMemo(() => ({ evidence: dashboard.evidence.status === 'error' ? 1 : 0 }), [dashboard.evidence.status]);

  const open = useCallback((symbol: string) => onOpenTicker(symbol, 'symbol'), [onOpenTicker]);
  const toggleRail = useCallback(() => {
    const next = !collapsed;
    setRailPreference(next);
    saveRailPreference(next);
  }, [collapsed]);

  const railEntries = useMemo(
    () => buildWorkstationRail(watchlist, dashboard.portfolio.data.positions, morningBrief.brief?.movers ?? []),
    [dashboard.portfolio.data.positions, morningBrief.brief?.movers, watchlist],
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
  const tabsRef = useRef(tabs);
  tabsRef.current = tabs;

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      // Text fields and dialogs own every key; a focused button or link owns only Enter, so
      // clicking a tab never switches the shortcuts off.
      const typing = Boolean(
        target
          && (target.tagName === 'INPUT'
            || target.tagName === 'TEXTAREA'
            || target.tagName === 'SELECT'
            || target.isContentEditable
            || target.closest('[role="dialog"]')),
      );
      const focusedControl = Boolean(target && (target.tagName === 'BUTTON' || target.tagName === 'A'));
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (typing || jumpOpenRef.current) return;

      const key = event.key;
      if (key === '/') {
        setJumpOpen(true);
        event.preventDefault();
        return;
      }
      if (/^[1-9]$/.test(key)) {
        const sections = tabsRef.current.filter((tab) => tab.id !== 'watchlist');
        const next = sections[Number(key) - 1];
        if (next) {
          onSelectSection(next.id);
          event.preventDefault();
        }
        return;
      }
      if (key === 'j' || key === 'k') {
        const symbols = railEntriesRef.current.map((entry) => entry.symbol);
        const next = stepSymbols(symbols, railCursorRef.current, key === 'j' ? 1 : -1);
        if (next) {
          setRailCursor(next);
          event.preventDefault();
        }
        return;
      }
      if (key === 'Enter' && railCursorRef.current && !focusedControl) {
        open(railCursorRef.current);
        event.preventDefault();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onSelectSection, open]);

  const briefing = dashboard.briefing.data;
  const activeRegime = read?.regime ?? dashboard.regime.data.current;

  return (
    <div className="mw" data-density={density}>
      <MarketBar
        regime={activeRegime}
        regimeReasoning={read?.regimeReasoning}
        live={live}
        asOf={dashboard.asOf}
        vix={briefing.vix}
        breadthPct={briefing.breadthPct}
        refreshing={refreshing}
        onRefresh={() => void refresh()}
        density={density}
        onDensity={setDensity}
        onJump={() => setJumpOpen(true)}
      />

      <div className="mw-body">
        {!railHidden && (
          <WatchRail
            watchlist={watchlist}
            entries={railEntries}
            cursor={railCursor}
            collapsed={collapsed}
            onToggle={toggleRail}
            onSelect={open}
          />
        )}

        <div className="mw-main">
          <MarketSectionTabs tabs={tabs} active={active} onSelect={onSelectSection} newCounts={newCounts} warnings={warnings} />

          <div className="mw-section" key={active}>
            {active === 'briefing' && (
              <BriefingSection
                dashboard={dashboard}
                brief={morningBrief.brief}
                generating={morningBrief.generating}
                onRunSweep={() => void morningBrief.runNow()}
                read={read}
                reading={reading}
                readError={readError}
                onRunRead={() => void runRead()}
                onExplain={() => setReasoningOpen(true)}
                onOpen={open}
                onGoTo={onSelectSection}
                calendar={economicCalendar}
                ledger={forwardLedger.report}
              />
            )}
            {active === 'structure' && <StructureSection dashboard={dashboard} read={read} onOpen={open} isMobile={isMobile} />}
            {active === 'signals' && <SignalsSection dashboard={dashboard} onOpen={open} isMobile={isMobile} />}
            {active === 'portfolio' && (
              <PortfolioSection dashboard={dashboard} read={read} tradeLedger={tradeLedger} onSyncWebull={() => void syncWebull()} syncing={webullSyncing} onOpen={open} isMobile={isMobile} />
            )}
            {active === 'evidence' && <EvidenceSection dashboard={dashboard} watched={watchlist.symbols} onOpen={open} />}
            {active === 'ledger' && <LedgerSection report={forwardLedger.report} loading={forwardLedger.loading} />}
            {active === 'backtest' && <BacktestSection />}
            {active === 'watchlist' && (
              <WatchRail variant="sheet" watchlist={watchlist} entries={railEntries} cursor={railCursor} collapsed={false} onToggle={toggleRail} onSelect={open} />
            )}
          </div>

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

      {reasoningOpen && <BriefingReasoning dash={dashboard} read={read} sessions={marketSessions} onClose={() => setReasoningOpen(false)} />}
    </div>
  );
}
