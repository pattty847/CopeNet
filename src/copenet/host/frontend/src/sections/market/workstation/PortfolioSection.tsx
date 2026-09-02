// Portfolio — the whole "my money" subject in one place: positions, the speculative lane,
// all-time P&L and every fill. The brief's Book row is the glance; this is the room.

import { useMemo } from 'react';
import { AllTimePnl } from '../AllTimePnl';
import { Portfolio, Speculative } from '../panelsLists';
import { TradeHistory } from '../TradeHistory';
import { ArrangeMenu, SectionGrid, SectionHeader, useSectionLayout, type SectionPanel } from './SectionGrid';
import type { TradeLedgerState } from '../useMarketMonitorData';
import type { DashboardPayload, MarketRead } from '../types';

export function PortfolioSection({
  dashboard,
  read,
  tradeLedger,
  onSyncWebull,
  syncing,
  onOpen,
  isMobile,
}: {
  dashboard: DashboardPayload;
  read: MarketRead | null;
  tradeLedger: TradeLedgerState;
  onSyncWebull: () => void;
  syncing: boolean;
  onOpen: (symbol: string) => void;
  isMobile: boolean;
}) {
  const panels = useMemo<SectionPanel[]>(
    () => [
      { id: 'positions', title: 'Positions · live P&L', defaultWidth: 'full', canHalf: false, node: <Portfolio panel={dashboard.portfolio} onOpen={onOpen} onSyncWebull={onSyncWebull} syncing={syncing} /> },
      { id: 'speculative', title: 'Speculative lane', defaultWidth: 'half', canHalf: true, node: <Speculative panel={dashboard.speculative} onOpen={onOpen} comment={read?.speculativeComment} /> },
      {
        id: 'allTimePnl',
        title: 'All-time P&L',
        defaultWidth: 'half',
        canHalf: true,
        node: <AllTimePnl ledger={tradeLedger.ledger} loading={tradeLedger.loading} syncing={tradeLedger.syncing} error={tradeLedger.error} onSync={() => void tradeLedger.sync()} onOpen={onOpen} />,
      },
      { id: 'tradeHistory', title: 'Trade history', defaultWidth: 'full', canHalf: false, node: <TradeHistory ledger={tradeLedger.ledger} loading={tradeLedger.loading} onOpen={onOpen} /> },
    ],
    [dashboard.portfolio, dashboard.speculative, onOpen, onSyncWebull, read?.speculativeComment, syncing, tradeLedger],
  );
  const layout = useSectionLayout('portfolio', panels);
  const positions = dashboard.portfolio.data.positions.length;

  return (
    <>
      <SectionHeader label="Portfolio" meta={`${positions} open position${positions === 1 ? '' : 's'}`}>
        {!isMobile && <ArrangeMenu layout={layout} />}
      </SectionHeader>
      <SectionGrid layout={layout} isMobile={isMobile} />
    </>
  );
}
