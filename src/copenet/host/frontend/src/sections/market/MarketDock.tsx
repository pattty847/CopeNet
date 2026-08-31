// The market research dock.
//
// Everything that used to be a draggable card mosaic is now a docked destination: sibling
// analytical modes that benefit from staying under the orientation stage, one keypress
// (\) from collapsed to half to full. Only the active tab renders, so opening the cockpit
// costs the brief and the tape — never seven panels of chart work.
//
// The model read threads through here the way the philosophy asks: rotation commentary on
// the RRG, the speculative comment on the spec lane, thesis-killers beside the evidence.

import { ResearchDrawer } from './ResearchDrawer';
import { MARKET_DOCK_TABS, type DockSnap, type MarketDockTab } from './marketCockpitState';
import { AllTimePnl } from './AllTimePnl';
import { BacktestLab } from './BacktestLab';
import { ForwardLedger } from './ForwardLedger';
import { AccumulationWatch, Contrarian, Evidence, Portfolio, SoftBottomingWatch, Speculative, TrendWatch } from './panelsLists';
import { Rrg } from './RrgChart';
import { TradeHistory } from './TradeHistory';
import { TreasuryYieldCurve } from './TreasuryYieldCurve';
import type { TradeLedgerState } from './useMarketMonitorData';
import type { DashboardPayload, LedgerReport, MarketRead } from './types';

export function MarketDock({
  tab,
  onTab,
  snap,
  onSnap,
  size,
  onResize,
  onCycleSnap,
  dash,
  read,
  onOpen,
  tradeLedger,
  ledger,
  ledgerLoading,
  onSyncWebull,
  webullSyncing,
}: {
  tab: MarketDockTab;
  onTab: (tab: MarketDockTab) => void;
  snap: DockSnap;
  onSnap: (snap: DockSnap) => void;
  size?: number;
  onResize: (size: number) => void;
  onCycleSnap: () => void;
  dash: DashboardPayload;
  read: MarketRead | null;
  onOpen: (symbol: string) => void;
  tradeLedger: TradeLedgerState;
  ledger: LedgerReport | null;
  ledgerLoading: boolean;
  onSyncWebull: () => void;
  webullSyncing: boolean;
}) {
  const evidenceWarnings = dash.evidence.status === 'error' ? 1 : 0;

  return (
    <ResearchDrawer
      tab={tab}
      onTab={onTab}
      entries={MARKET_DOCK_TABS}
      snap={snap}
      onSnap={onSnap}
      size={size}
      onResize={onResize}
      onCycleSnap={onCycleSnap}
      warnings={{ evidence: evidenceWarnings }}
    >
      {tab === 'rotation' && (
        <div className="mc-dock-grid">
          <Rrg panel={dash.rrg} onOpen={onOpen} note={read?.rotationRead} />
          {dash.industryRrg && (
            <Rrg
              panel={dash.industryRrg}
              onOpen={onOpen}
              title="Industry Rotation · RRG"
              subtitle="Regional banks, biotech, retail, homebuilders, defense vs S&P 500 · weekly"
            />
          )}
        </div>
      )}

      {tab === 'rates' && <TreasuryYieldCurve />}

      {tab === 'portfolio' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className="mc-dock-grid">
            <Portfolio panel={dash.portfolio} onOpen={onOpen} onSyncWebull={onSyncWebull} syncing={webullSyncing} />
            <AllTimePnl
              ledger={tradeLedger.ledger}
              loading={tradeLedger.loading}
              syncing={tradeLedger.syncing}
              error={tradeLedger.error}
              onSync={() => void tradeLedger.sync()}
              onOpen={onOpen}
            />
          </div>
          <TradeHistory ledger={tradeLedger.ledger} loading={tradeLedger.loading} onOpen={onOpen} />
        </div>
      )}

      {tab === 'evidence' && (
        <div className="mc-dock-grid">
          <Evidence panel={dash.evidence} onOpen={onOpen} />
          <Contrarian
            panel={
              read && read.thesisKillers.length
                ? { status: 'live', data: read.thesisKillers, note: 'model read' }
                : dash.contrarian
            }
          />
        </div>
      )}

      {tab === 'signals' && (
        <div className="mc-dock-grid">
          <AccumulationWatch panel={dash.accumulation} onOpen={onOpen} />
          <TrendWatch panel={dash.trend} onOpen={onOpen} />
          <SoftBottomingWatch panel={dash.softBottoming} onOpen={onOpen} />
          <Speculative panel={dash.speculative} onOpen={onOpen} comment={read?.speculativeComment} />
        </div>
      )}

      {tab === 'ledger' && <ForwardLedger report={ledger} loading={ledgerLoading} />}

      {tab === 'backtest' && <BacktestLab />}
    </ResearchDrawer>
  );
}
