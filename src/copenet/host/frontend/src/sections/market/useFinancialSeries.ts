import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { FinancialFrequency, OverlaySeriesPayload } from './types';

export const FINANCIAL_SERIES_CACHE_TTL_MS = 5 * 60 * 1000;

export interface FinancialSeriesCacheEntry {
  data: OverlaySeriesPayload | null;
  cachedAt: number;
}

const cache = new Map<string, FinancialSeriesCacheEntry>();

export function isFinancialSeriesCacheEntryFresh(
  entry: FinancialSeriesCacheEntry,
  now: number = Date.now(),
): boolean {
  return now - entry.cachedAt < FINANCIAL_SERIES_CACHE_TTL_MS;
}

export interface FinancialSeriesState {
  data: OverlaySeriesPayload | null;
  loading: boolean;
  loaded: boolean;
  error: string | null;
}

export function useFinancialSeries(
  symbol: string,
  metric: string,
  frequency: FinancialFrequency,
  enabled: boolean,
): FinancialSeriesState {
  const normalized = symbol.trim().toUpperCase();
  const key = `${normalized}:${metric}:${frequency}:canonical:availability`;
  const generation = useRef(0);
  const [state, setState] = useState<FinancialSeriesState>({
    data: null,
    loading: false,
    loaded: false,
    error: null,
  });

  useEffect(() => {
    generation.current += 1;
    const requestGeneration = generation.current;
    if (!enabled || !normalized) {
      setState((current) => ({ ...current, loading: false, error: null }));
      return;
    }
    const cached = cache.get(key);
    if (cached && isFinancialSeriesCacheEntryFresh(cached)) {
      setState({ data: cached.data, loading: false, loaded: true, error: null });
      return;
    }
    if (cached) cache.delete(key);
    setState({ data: null, loading: true, loaded: false, error: null });
    wsClient
      .marketFinancialSeries(normalized, metric, frequency)
      .then((data) => {
        if (generation.current !== requestGeneration) return;
        cache.set(key, { data, cachedAt: Date.now() });
        setState({ data, loading: false, loaded: true, error: null });
      })
      .catch((error: unknown) => {
        if (generation.current !== requestGeneration) return;
        const message = error instanceof Error ? error.message : 'Financial series request failed';
        setState({ data: null, loading: false, loaded: true, error: message });
      });
  }, [enabled, frequency, key, metric, normalized]);

  return state;
}
