// Client RPC layer for the Market Monitor (blueprint §1). The backend emits camelCase JSON that
// already matches the typed contract in sections/market/types.ts, so these helpers just pass the
// payload through. This is the only place the frontend touches the market.* wire methods.

import type {
  DashboardPayload,
  LedgerReport,
  MarketRead,
  MorningBriefPayload,
  TickerEvidencePayload,
  TickerFundamentals,
  SymbolSearchResult,
  TickerDetailPayload,
  TickerRead,
  UniverseAsset,
  WatchlistItem,
} from '../sections/market/types';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function marketDashboardRpc(request: WsRpcRequest): Promise<DashboardPayload> {
  const payload = await request<Record<string, unknown>>('market.dashboard.get', {});
  return payload as unknown as DashboardPayload;
}

export async function marketTickerRpc(request: WsRpcRequest, symbol: string): Promise<TickerDetailPayload> {
  const payload = await request<Record<string, unknown>>('market.ticker.get', { symbol });
  return payload as unknown as TickerDetailPayload;
}

export async function marketTickerEvidenceRpc(request: WsRpcRequest, symbol: string, refresh = false): Promise<TickerEvidencePayload> {
  const payload = await request<Record<string, unknown>>('market.ticker.evidence.get', { symbol, refresh });
  return payload as unknown as TickerEvidencePayload;
}

export async function marketUniverseRpc(request: WsRpcRequest): Promise<UniverseAsset[]> {
  const payload = await request<Record<string, unknown>>('market.universe.get', {});
  if (Array.isArray(payload)) return payload as unknown as UniverseAsset[];
  const wrapped = payload as { universe?: unknown; assets?: unknown };
  const arr = Array.isArray(wrapped.universe) ? wrapped.universe : Array.isArray(wrapped.assets) ? wrapped.assets : [];
  return arr as UniverseAsset[];
}

export async function marketRefreshRpc(
  request: WsRpcRequest,
  scope: 'all' | 'macro' | 'signals' | 'edgar' = 'all',
): Promise<{ startedAt: string; runId: string }> {
  const payload = await request<Record<string, unknown>>('market.refresh', { scope });
  return { startedAt: String(payload.startedAt || ''), runId: String(payload.runId || '') };
}

export async function marketInterpretRpc(
  request: WsRpcRequest,
  target: string = 'market',
): Promise<{ startedAt: string; runId: string }> {
  const payload = await request<Record<string, unknown>>('market.interpret', { target });
  return { startedAt: String(payload.startedAt || ''), runId: String(payload.runId || '') };
}

export async function marketTickerFundamentalsRpc(request: WsRpcRequest, symbol: string): Promise<TickerFundamentals | null> {
  const payload = await request<{ fundamentals?: unknown }>('market.ticker.fundamentals.get', { symbol });
  const fundamentals = payload.fundamentals;
  return fundamentals && typeof fundamentals === 'object' ? (fundamentals as TickerFundamentals) : null;
}

export async function marketLedgerGetRpc(request: WsRpcRequest): Promise<LedgerReport> {
  const payload = await request<Record<string, unknown>>('market.ledger.get', {});
  return payload as unknown as LedgerReport;
}

export async function marketBriefGetRpc(request: WsRpcRequest): Promise<MorningBriefPayload | null> {
  const payload = await request<{ brief?: unknown }>('market.brief.get', {});
  const brief = payload.brief;
  return brief && typeof brief === 'object' ? (brief as MorningBriefPayload) : null;
}

export async function marketBriefRunRpc(request: WsRpcRequest, force = true): Promise<{ startedAt: string }> {
  const payload = await request<Record<string, unknown>>('market.brief.run', { force });
  return { startedAt: String(payload.startedAt || '') };
}

export interface WebullStatus {
  configured: boolean;
  auth?: { authenticated?: boolean; status?: string } | null;
  account?: { accountId: string } | null;
  lastSync?: string | null;
  positionCount?: number;
}

export async function marketWebullStatusRpc(request: WsRpcRequest): Promise<WebullStatus> {
  const payload = await request<Record<string, unknown>>('market.webull.status', {});
  return payload as unknown as WebullStatus;
}

export async function marketWebullSyncRpc(request: WsRpcRequest): Promise<{ startedAt: string }> {
  const payload = await request<Record<string, unknown>>('market.webull.sync', {});
  return { startedAt: String(payload.startedAt || '') };
}

export async function marketReadGetRpc(
  request: WsRpcRequest,
  target: string = 'market',
): Promise<MarketRead | TickerRead | null> {
  const payload = await request<{ read?: unknown }>('market.read.get', { target });
  const read = payload.read;
  return read && typeof read === 'object' ? (read as MarketRead | TickerRead) : null;
}

export interface BacktestPayload {
  portfolioSeries: { date: string; value: number }[];
  benchmarkSeries: { date: string; value: number }[];
  metrics: {
    total_return: number;
    benchmark_total_return: number;
    max_drawdown: number;
    benchmark_max_drawdown: number;
    volatility: number;
    benchmark_volatility: number;
    sharpe: number;
    benchmark_sharpe: number;
    beta: number;
    correlation: number;
  };
  metadata: {
    symbols?: string[];
    weights?: number[];
    startDate?: string;
    endDate?: string;
    rebalanceMode?: string;
    rebalanceInterval?: string | null;
    benchmark?: string;
    scenarioName?: string;
    scenarioKey?: string;
    durationWeeks?: number;
    shockDetails?: Record<string, number>;
    usedFallbackPositions?: boolean;
  };
}

export async function marketBacktestRunRpc(
  request: WsRpcRequest,
  params: {
    sessionKey: string;
    symbols: string[];
    weights: number[];
    startDate: string;
    endDate: string;
    benchmark?: string;
    rebalance?: string;
    rebalanceInterval?: string | null;
  }
): Promise<BacktestPayload> {
  const payload = await request<Record<string, unknown>>('market.backtest.run', params as any);
  return payload as unknown as BacktestPayload;
}

export interface WatchlistWireState {
  items: WatchlistItem[];
  lists: string[];
  active: string;
}

function watchlistState(payload: { items?: unknown; lists?: unknown; active?: unknown }): WatchlistWireState {
  return {
    items: Array.isArray(payload.items) ? (payload.items as WatchlistItem[]) : [],
    lists: Array.isArray(payload.lists) ? (payload.lists as string[]) : ['Default'],
    active: typeof payload.active === 'string' && payload.active ? payload.active : 'Default',
  };
}

export async function marketWatchlistGetRpc(request: WsRpcRequest): Promise<WatchlistWireState> {
  return watchlistState(await request<Record<string, unknown>>('market.watchlist.get', {}));
}

export async function marketWatchlistAddRpc(request: WsRpcRequest, symbol: string, name = ''): Promise<WatchlistWireState> {
  return watchlistState(await request<Record<string, unknown>>('market.watchlist.add', { symbol, name }));
}

export async function marketWatchlistRemoveRpc(request: WsRpcRequest, symbol: string): Promise<WatchlistWireState> {
  return watchlistState(await request<Record<string, unknown>>('market.watchlist.remove', { symbol }));
}

export async function marketWatchlistListCreateRpc(request: WsRpcRequest, name: string): Promise<WatchlistWireState> {
  return watchlistState(await request<Record<string, unknown>>('market.watchlist.list.create', { name }));
}

export async function marketWatchlistListDeleteRpc(request: WsRpcRequest, name: string): Promise<WatchlistWireState> {
  return watchlistState(await request<Record<string, unknown>>('market.watchlist.list.delete', { name }));
}

export async function marketWatchlistListSelectRpc(request: WsRpcRequest, name: string): Promise<WatchlistWireState> {
  return watchlistState(await request<Record<string, unknown>>('market.watchlist.list.select', { name }));
}

export async function marketSymbolsSearchRpc(request: WsRpcRequest, query: string, limit = 8): Promise<SymbolSearchResult[]> {
  const payload = await request<{ results?: unknown }>('market.symbols.search', { query, limit });
  return Array.isArray(payload.results) ? (payload.results as SymbolSearchResult[]) : [];
}

export async function marketBacktestStressTestRpc(
  request: WsRpcRequest,
  params: {
    sessionKey: string;
    scenarioKey: string;
    positions: any[];
  }
): Promise<BacktestPayload> {
  const payload = await request<Record<string, unknown>>('market.backtest.stress_test', params as any);
  return payload as unknown as BacktestPayload;
}
