import { useState, type ReactNode } from 'react';
import { useIsMobile } from '../../lib/responsive';
import { AllTimePnl } from './AllTimePnl';
import { BacktestLab } from './BacktestLab';
import { BriefingReasoning } from './BriefingReasoning';
import { EconomicCalendarWidget } from './EconomicCalendarWidget';
import { ForwardLedger } from './ForwardLedger';
import { MarketGrid } from './MarketGrid';
import { MM } from './marketUi';
import { MorningBrief } from './MorningBrief';
import { AccumulationWatch, Contrarian, Evidence, Portfolio, SoftBottomingWatch, Speculative, TrendWatch, Watchlist } from './panelsLists';
import { BriefingHero, MacroBoard } from './panelsTop';
import { Rrg } from './RrgChart';
import { TickerSearch } from './TickerSearch';
import { TradeHistory } from './TradeHistory';
import { TreasuryYieldCurve } from './TreasuryYieldCurve';
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

const DETAIL_OPEN_KEY = 'copenet.market.detailOpen';
const MARKET_GRID_STORAGE_KEY = 'copenet.market.gridLayout.v1';

function MarketDetail({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(DETAIL_OPEN_KEY) === '1';
    } catch {
      return false;
    }
  });
  const toggle = () =>
    setOpen((value) => {
      const next = !value;
      try {
        localStorage.setItem(DETAIL_OPEN_KEY, next ? '1' : '0');
      } catch {
        // Private browsing can make storage unavailable.
      }
      return next;
    });

  return (
    <>
      <button
        onClick={toggle}
        style={{ cursor: 'pointer', width: '100%', textAlign: 'left', border: `1px solid ${MM.border}`, background: 'rgba(254,252,244,.02)', color: MM.muted, borderRadius: 12, padding: '11px 14px', font: '600 10.5px Inter', letterSpacing: '.08em', textTransform: 'uppercase' }}
      >
        {open ? '▾' : '▸'} Market detail
        <span style={{ color: MM.dimmer, fontWeight: 500, textTransform: 'none', letterSpacing: '.02em', marginLeft: 8 }}>
          watchlist · macro · rotation · portfolio · P&amp;L · trade history · evidence
        </span>
      </button>
      {open && children}
    </>
  );
}

export function MarketDashboard({
  onOpenTicker,
  watchlist,
}: {
  onOpenTicker: (symbol: string, type?: 'symbol' | 'formula') => void;
  watchlist: MarketWatchlistState;
}) {
  const { dashboard: dash, refreshing, live, refresh, reload } = useMarketDashboard();
  const { read: marketRead, running: reading, run: runRead } = useMarketRead();
  const marketSessions = useMarketSessions();
  const morningBrief = useMorningBrief(reload);
  const economicCalendar = useEconomicCalendar();
  const ledger = useForwardLedger();
  const tradeLedger = useTradeLedger();
  const isMobile = useIsMobile();
  const [reasoningOpen, setReasoningOpen] = useState(false);
  const [webullSyncing, setWebullSyncing] = useState(false);
  const [activeTab, setActiveTab] = useState<'monitor' | 'backtest'>('monitor');

  const syncWebull = async () => {
    setWebullSyncing(true);
    try {
      const { wsClient } = await import('../../lib/wsClient');
      await wsClient.marketWebullSync();
      for (let attempt = 0; attempt < 8; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 5000));
        await reload();
      }
    } catch {
      // The dashboard refresh will expose the last healthy broker state.
    } finally {
      setWebullSyncing(false);
    }
  };

  const open = (symbol: string) => onOpenTicker(symbol, 'symbol');

  return (
    <div style={{ background: MM.bg, minHeight: '100%', color: MM.text }}>
      <div className="market-dashboard-canvas">
        <div style={{ display: 'flex', flexDirection: isMobile ? 'column' : 'row', alignItems: isMobile ? 'stretch' : 'center', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap' }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.muted, whiteSpace: 'nowrap' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: live ? MM.up : MM.dim, flex: '0 0 auto' }} />
              {live ? 'Live data' : 'Illustrative preview'} · {dash.asOf}
            </span>
            <div style={{ display: 'flex', gap: 4, background: '#050506', border: `1px solid ${MM.border}`, borderRadius: 8, padding: 3 }}>
              <button onClick={() => setActiveTab('monitor')} style={{ cursor: 'pointer', border: 'none', borderRadius: 5, padding: '4px 11px', font: '600 10.5px Inter', background: activeTab === 'monitor' ? MM.accent : 'transparent', color: activeTab === 'monitor' ? '#1a1205' : MM.muted }}>
                Monitor
              </button>
              <button onClick={() => setActiveTab('backtest')} style={{ cursor: 'pointer', border: 'none', borderRadius: 5, padding: '4px 11px', font: '600 10.5px Inter', background: activeTab === 'backtest' ? MM.accent : 'transparent', color: activeTab === 'backtest' ? '#1a1205' : MM.muted }}>
                Backtest Lab
              </button>
            </div>
          </div>
          {activeTab === 'monitor' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <button onClick={() => void runRead()} disabled={reading} style={{ cursor: reading ? 'default' : 'pointer', border: '1px solid rgba(90,143,199,.35)', background: 'rgba(90,143,199,.1)', color: '#8fb8e8', borderRadius: 9, padding: '7px 13px', font: '600 10px Inter', letterSpacing: '.05em', opacity: reading ? 0.6 : 1 }}>
                {reading ? '◍ Reading the tape…' : '✦ Model read'}
              </button>
              <button onClick={() => void refresh()} disabled={refreshing} style={{ cursor: refreshing ? 'default' : 'pointer', border: `1px solid ${MM.borderHi}`, background: MM.accentSoft, color: MM.accent, borderRadius: 9, padding: '7px 13px', font: '600 10px Inter', letterSpacing: '.05em', opacity: refreshing ? 0.6 : 1 }}>
                {refreshing ? '◍ Refreshing…' : '↻ Refresh data'}
              </button>
              <TickerSearch onSelect={(symbol, _name, type) => onOpenTicker(symbol, type)} fullWidth={isMobile} />
            </div>
          )}
        </div>

        {activeTab === 'backtest' ? (
          <BacktestLab />
        ) : (
          <>
            <MorningBrief
              brief={morningBrief.brief}
              generating={morningBrief.generating}
              onRunNow={() => void morningBrief.runNow()}
              onOpen={open}
              regime={dash.regime}
              ledger={ledger.report}
              onExplain={() => setReasoningOpen(true)}
              calendar={<EconomicCalendarWidget calendar={economicCalendar.calendar} loading={economicCalendar.loading} refreshing={economicCalendar.refreshing} error={economicCalendar.error} onRefresh={() => void economicCalendar.refresh()} />}
            />
            <BriefingHero panel={dash.briefing} onOpen={open} onExplain={() => setReasoningOpen(true)} read={marketRead} />
            <TreasuryYieldCurve />
            <MarketDetail>
              <MarketGrid
                storageKey={MARKET_GRID_STORAGE_KEY}
                panels={[
                  {
                    id: 'watchlist',
                    layout: { x: 0, y: 0, w: 5, h: 12, minW: 4, minH: 6 },
                    node: <Watchlist items={watchlist.items} lists={watchlist.lists} active={watchlist.active} loading={watchlist.loading} onOpen={open} onRemove={(symbol) => void watchlist.remove(symbol)} onAdd={(symbol, name) => void watchlist.add(symbol, name)} onSelectList={(name) => void watchlist.selectList(name)} onCreateList={(name) => void watchlist.createList(name)} onDeleteList={(name) => void watchlist.deleteList(name)} onImportWebull={() => void watchlist.importFromWebull()} importing={watchlist.importing} />,
                  },
                  { id: 'macro', layout: { x: 5, y: 0, w: 7, h: 12, minW: 4, minH: 6 }, node: <MacroBoard panel={dash.macro} /> },
                  ...(dash.softBottoming ? [{ id: 'softBottoming', layout: { x: 0, y: 12, w: 12, h: 8, minW: 4, minH: 5 }, node: <SoftBottomingWatch panel={dash.softBottoming} onOpen={open} /> }] : []),
                  { id: 'rrg', layout: { x: 0, y: 20, w: 7, h: 14, minW: 5, minH: 8 }, node: <Rrg panel={dash.rrg} onOpen={open} note={marketRead?.rotationRead} /> },
                  { id: 'accumulation', layout: { x: 7, y: 20, w: 5, h: 7, minW: 3, minH: 5 }, node: <AccumulationWatch panel={dash.accumulation} onOpen={open} /> },
                  { id: 'trend', layout: { x: 7, y: 27, w: 5, h: 7, minW: 3, minH: 5 }, node: <TrendWatch panel={dash.trend} onOpen={open} /> },
                  ...(dash.industryRrg ? [{ id: 'industryRrg', layout: { x: 0, y: 34, w: 7, h: 14, minW: 5, minH: 8 }, node: <Rrg panel={dash.industryRrg} onOpen={open} title="Industry Rotation · RRG" subtitle="Regional banks, biotech, retail, homebuilders, defense vs S&P 500 · weekly" /> }] : []),
                  { id: 'portfolio', layout: { x: 0, y: 34, w: 6, h: 13, minW: 4, minH: 6 }, node: <Portfolio panel={dash.portfolio} onOpen={open} onSyncWebull={() => void syncWebull()} syncing={webullSyncing} /> },
                  { id: 'allTimePnl', layout: { x: 6, y: 34, w: 6, h: 13, minW: 4, minH: 8 }, node: <AllTimePnl ledger={tradeLedger.ledger} loading={tradeLedger.loading} syncing={tradeLedger.syncing} error={tradeLedger.error} onSync={() => void tradeLedger.sync()} onOpen={open} /> },
                  { id: 'tradeHistory', layout: { x: 0, y: 47, w: 12, h: 13, minW: 4, minH: 6 }, node: <TradeHistory ledger={tradeLedger.ledger} loading={tradeLedger.loading} onOpen={open} /> },
                  { id: 'speculative', layout: { x: 0, y: 60, w: 6, h: 10, minW: 3, minH: 5 }, node: <Speculative panel={dash.speculative} onOpen={open} comment={marketRead?.speculativeComment} /> },
                  { id: 'forwardLedger', layout: { x: 6, y: 60, w: 6, h: 10, minW: 4, minH: 5 }, node: <ForwardLedger report={ledger.report} loading={ledger.loading} /> },
                  { id: 'evidence', layout: { x: 0, y: 70, w: 6, h: 12, minW: 4, minH: 5 }, node: <Evidence panel={dash.evidence} onOpen={open} /> },
                  { id: 'contrarian', layout: { x: 6, y: 70, w: 6, h: 12, minW: 3, minH: 5 }, node: <Contrarian panel={marketRead && marketRead.thesisKillers.length ? { status: 'live', data: marketRead.thesisKillers, note: 'model read' } : dash.contrarian} /> },
                ]}
              />
            </MarketDetail>
          </>
        )}
        <div style={{ textAlign: 'center', fontSize: 10.5, color: MM.dimmer, padding: '6px 0 14px' }}>
          Reads are evidence-based with caveats — never forecasts. Panels marked “preview” are illustrative until their live data loads.
        </div>
      </div>
      {reasoningOpen && <BriefingReasoning dash={dash} read={marketRead} sessions={marketSessions} onClose={() => setReasoningOpen(false)} />}
    </div>
  );
}
