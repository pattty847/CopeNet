import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { useAppStore } from '../../../store/useAppStore';
import type { ForecastRecord } from './types';

/** Stored records are reconciled after broadcasts and while visible, including reconnects. */
export function useForecasts(documentId?: string, enabled = true) {
  const connection = useAppStore((state) => state.wsStatus);
  const [records, setRecords] = useState<ForecastRecord[]>([]);
  const [pages, setPages] = useState(1);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const sequence = useRef(0);
  const scope = useRef(documentId); scope.current = documentId;
  const refresh = useCallback(async () => {
    if (connection !== 'connected' || !enabled) return;
    const requestSequence = ++sequence.current;
    try {
      const rows: ForecastRecord[] = [];
      let offset: number | null = 0;
      for (let page = 0; page < pages && offset != null; page += 1) {
        const response = await wsClient.marketForecast.list(documentId, offset);
        rows.push(...response.forecasts); offset = response.nextOffset;
      }
      if (scope.current !== documentId || requestSequence !== sequence.current) return;
      setRecords([...new Map(rows.map((record) => [record.forecastId, record])).values()]); setNextOffset(offset); setError(null);
    } catch (reason) {
      if (scope.current === documentId && requestSequence === sequence.current) setError(reason instanceof Error ? reason.message : 'Forecasts unavailable.');
    } finally { if (scope.current === documentId && requestSequence === sequence.current) setLoading(false); }
  }, [documentId, connection, enabled, pages]);
  useEffect(() => { setRecords([]); setLoading(true); setPages(1); setNextOffset(null); }, [documentId]);
  useEffect(() => {
    void refresh();
    const off = wsClient.marketForecast.subscribe(() => void refresh());
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void refresh(); }, 5000);
    return () => { sequence.current += 1; off(); window.clearInterval(timer); };
  }, [refresh]);
  return { records, loading, nextOffset, loadMore: () => setPages((count) => count + 1), error: connection === 'connected' ? error : 'Host disconnected', refresh };
}
