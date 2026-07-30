import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { FinancialFrequency, OverlaySeriesPayload } from './types';

const cache = new Map<string, OverlaySeriesPayload | null>();

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
    if (cache.has(key)) {
      setState({ data: cache.get(key) ?? null, loading: false, loaded: true, error: null });
      return;
    }
    setState({ data: null, loading: true, loaded: false, error: null });
    wsClient
      .marketFinancialSeries(normalized, metric, frequency)
      .then((data) => {
        if (generation.current !== requestGeneration) return;
        cache.set(key, data);
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
