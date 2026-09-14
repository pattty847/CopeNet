import { useCallback } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { useStoredMarketResource } from '../useStoredMarketResource';
export function usePosition(symbol: string) {
  const fetcher = useCallback(() => wsClient.marketPosition.get(symbol), [symbol]);
  const state = useStoredMarketResource(fetcher);
  return { ...state, data: state.data?.symbol === symbol ? state.data : null };
}
