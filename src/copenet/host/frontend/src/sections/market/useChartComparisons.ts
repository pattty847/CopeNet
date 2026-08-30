import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { ChartFormulasPayload } from './types';
import type { ChartTimeframe } from './chartRanges';

const RPC_TIMEFRAME: Record<ChartTimeframe, ChartFormulasPayload['timeframe']> = { D: 'daily', W: 'weekly', M: 'monthly' };

export function useChartComparisons(expressions: string[], timeframe: ChartTimeframe) {
  const requestKey = `${RPC_TIMEFRAME[timeframe]}:${expressions.join(',')}`;
  const [payload, setPayload] = useState<ChartFormulasPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);

  useEffect(() => {
    const version = ++requestVersion.current;
    if (!expressions.length) {
      setPayload(null);
      setLoading(false);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    setPayload(null);
    void wsClient.marketChartFormulas(expressions, RPC_TIMEFRAME[timeframe])
      .then((next) => {
        if (requestVersion.current === version) setPayload(next);
      })
      .catch((reason) => {
        if (requestVersion.current === version) {
          setPayload(null);
          setError(reason instanceof Error ? reason.message : 'Formula history is unavailable.');
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
