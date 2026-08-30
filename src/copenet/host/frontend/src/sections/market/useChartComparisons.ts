import { useEffect, useMemo, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { comparisonSymbols } from './chartComparison';
import type { ChartSeriesPayload } from './types';
import type { ChartTimeframe } from './chartRanges';

const RPC_TIMEFRAME: Record<ChartTimeframe, ChartSeriesPayload['timeframe']> = { D: 'daily', W: 'weekly', M: 'monthly' };

export function useChartComparisons(expressions: string[], timeframe: ChartTimeframe) {
  const symbols = useMemo(() => comparisonSymbols(expressions), [expressions]);
  const requestKey = `${RPC_TIMEFRAME[timeframe]}:${symbols.join(',')}`;
  const [payload, setPayload] = useState<ChartSeriesPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);

  useEffect(() => {
    const version = ++requestVersion.current;
    if (!symbols.length) {
      setPayload(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    void wsClient.marketChartSeries(symbols, RPC_TIMEFRAME[timeframe])
      .then((next) => {
        if (requestVersion.current === version) setPayload(next);
      })
      .catch((reason) => {
        if (requestVersion.current === version) {
          setPayload(null);
          setError(reason instanceof Error ? reason.message : 'Comparison history is unavailable.');
        }
      })
      .finally(() => {
        if (requestVersion.current === version) setLoading(false);
      });
    return () => {
      requestVersion.current += 1;
    };
  }, [requestKey]);

  return { payload, loading, error };
}
