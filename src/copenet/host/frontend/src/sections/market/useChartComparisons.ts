import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { ChartFormulasPayload } from './types';
import { isIntradayTimeframe, type ChartTimeframe } from './chartRanges';

/** Comparison formulas are computed from the daily cache, so they exist for D/W/M only.
 *  An intraday chart resolves to `daily` for the request key and is simply not asked for —
 *  see the guard in the hook. Silently plotting a daily ratio over 5m candles would be a
 *  comparison line that does not describe the chart it sits on. */
const RPC_TIMEFRAME: Record<'D' | 'W' | 'M', ChartFormulasPayload['timeframe']> = { D: 'daily', W: 'weekly', M: 'monthly' };

function rpcTimeframe(timeframe: ChartTimeframe): ChartFormulasPayload['timeframe'] {
  return isIntradayTimeframe(timeframe) ? 'daily' : RPC_TIMEFRAME[timeframe];
}

export function useChartComparisons(expressions: string[], timeframe: ChartTimeframe) {
  // Intraday has no comparison series; asking for none keeps the hook inert there.
  const scoped = isIntradayTimeframe(timeframe) ? [] : expressions;
  const requestKey = `${rpcTimeframe(timeframe)}:${scoped.join(',')}`;
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
