// Client RPC layer for the Market Monitor (blueprint §1). The backend emits camelCase JSON that
// already matches the typed contract in sections/market/types.ts, so these helpers just pass the
// payload through. This is the only place the frontend touches the market.* wire methods.

import type { DashboardPayload, TickerDetailPayload, UniverseAsset } from '../sections/market/types';

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
