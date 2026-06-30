// THE SEAM (blueprint §4). The entire Market Monitor UI reads through this hook.
// Today it returns illustrative sample data. When Codex's backend lands, this file is the ONLY
// place that changes: swap the sample imports for market.* RPC calls (panel-by-panel). Components
// never change — they always consume the typed contract from ./types.

import { SAMPLE_DASHBOARD, SAMPLE_UNIVERSE, sampleTicker } from './sampleData';
import type { DashboardPayload, TickerDetailPayload, UniverseAsset } from './types';

export function useMarketDashboard(): DashboardPayload {
  // TODO(backend): replace with `market.dashboard.get` via wsMarketRpc once panels go live.
  return SAMPLE_DASHBOARD;
}

export function useMarketUniverse(): UniverseAsset[] {
  // TODO(backend): replace with `market.universe.get`.
  return SAMPLE_UNIVERSE;
}

export function useTickerDetail(symbol: string): TickerDetailPayload {
  // TODO(backend): replace with `market.ticker.get { symbol }`.
  return sampleTicker(symbol);
}
