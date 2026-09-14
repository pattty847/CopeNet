import type { PositionPayload } from '../sections/market/position/types';
type Request = <T extends Record<string, unknown>>(method: string, params: Record<string, unknown>) => Promise<T>;
export function createMarketPositionApi(request: Request) {
  return { get: async (symbol: string) => await request('market.position.get', { symbol }) as unknown as PositionPayload };
}
