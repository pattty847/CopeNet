// The intraday read, on the chart's terms.
//
// Held apart from `useTickerViewModel` because the two lanes have genuinely different
// shapes: daily/weekly/monthly ride inside `ticker.detail` and are already in memory when
// the ticker opens, while an intraday interval is a separate request that should not happen
// at all unless the operator selects one.

import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { IntradaySession, IntradaySeries } from '../../types/backend';
import { isIntradayTimeframe, type ChartTimeframe } from './chartRanges';

export interface IntradayState {
  series: IntradaySeries | null;
  loading: boolean;
  error: string | null;
  /** True only for 1m, the one grain the vendor caps per request. */
  canLoadEarlier: boolean;
  loadEarlier: () => void;
  refresh: () => void;
}

//: One page beyond what is held, in vendor terms. 1m serves 7 days a request and 30 total.
const PAGE_DAYS = 7;

export function useIntradayBars(symbol: string, timeframe: ChartTimeframe): IntradayState {
  const active = isIntradayTimeframe(timeframe);
  const [series, setSeries] = useState<IntradaySeries | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [days, setDays] = useState<number | undefined>(undefined);
  // Which (symbol, interval) the current `series` describes. Without it a stale response
  // from the previous symbol paints over the incoming one — the same failure the view model
  // documents for Form 4 markers.
  const wanted = useRef('');

  const load = useCallback((requestedDays: number | undefined, refresh: boolean) => {
    if (!active) return;
    const key = `${symbol}|${timeframe}|${requestedDays ?? ''}`;
    wanted.current = key;
    setLoading(true);
    setError(null);
    void wsClient
      .marketIntraday({ symbol, interval: timeframe, session: 'all', days: requestedDays, refresh })
      .then((next) => {
        if (wanted.current !== key) return;
        setSeries(next);
        // The vendor refusing a grain outright is a state, not an error to swallow: its
        // message carries the real ceiling.
        setError(next.unavailable);
      })
      .catch((cause) => {
        if (wanted.current !== key) return;
        setError(cause instanceof Error ? cause.message : 'Could not load intraday bars.');
      })
      .finally(() => {
        if (wanted.current === key) setLoading(false);
      });
  }, [active, symbol, timeframe]);

  // Switching symbol or interval discards the previous answer rather than showing it under
  // the new heading while the request is in flight.
  useEffect(() => {
    if (!active) {
      setSeries(null);
      setError(null);
      setDays(undefined);
      return;
    }
    setSeries(null);
    setDays(undefined);
    load(undefined, false);
  }, [active, load]);

  const loadEarlier = useCallback(() => {
    const next = (days ?? PAGE_DAYS) + PAGE_DAYS;
    setDays(next);
    load(next, false);
  }, [days, load]);

  return {
    series,
    loading,
    error,
    // Only 1m is paged, and only until its window is exhausted. Offering the control on a
    // grain that already holds everything would be a button that cannot do anything.
    canLoadEarlier: Boolean(
      series && series.grain === '1m' && (days ?? PAGE_DAYS) < series.windowDays,
    ),
    loadEarlier,
    refresh: useCallback(() => load(days, true), [days, load]),
  };
}

export const INTRADAY_SESSION_DEFAULT: IntradaySession = 'all';
