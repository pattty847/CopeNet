import { useCallback, useEffect, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { EconomicCalendarPayload } from './types';

export interface EconomicCalendarState {
  calendar: EconomicCalendarPayload | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useEconomicCalendar(): EconomicCalendarState {
  const [calendar, setCalendar] = useState<EconomicCalendarPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (refresh: boolean) => {
    if (refresh) setRefreshing(true);
    try {
      const next = await wsClient.marketCalendarGet(7, refresh);
      setCalendar(next);
      setError(next.error ?? null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Economic calendar unavailable.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load(false);
  }, [load]);

  const refresh = useCallback(() => load(true), [load]);
  return { calendar, loading, refreshing, error, refresh };
}
