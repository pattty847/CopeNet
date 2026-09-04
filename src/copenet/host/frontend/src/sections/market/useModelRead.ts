import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { MarketRead, TickerRead } from './types';

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** Generic model-read lane (Insight Engine Phase D): load the stored read, and expose a
 *  trigger that kicks market.interpret then polls market.read.get until a FRESH read lands
 *  (generatedAt advances). The model call runs server-side in the background. */
export function useModelRead<T extends MarketRead | TickerRead>(target: string) {
  const [read, setRead] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const [retryKey, setRetryKey] = useState(0);
  useEffect(() => {
    let current = true;
    alive.current = true;
    setLoading(true);
    setRead(null);
    setError(null);
    wsClient
      .marketReadGet(target)
      .then((next) => {
        if (current && next) setRead(next as T);
      })
      .catch((caught) => {
        if (current)
          setError(
            caught instanceof Error ? caught.message : 'The saved model read could not be loaded. Retry after checking the connection.',
          );
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
      alive.current = false;
    };
  }, [target, retryKey]);

  const run = useCallback(async () => {
    setRunning(true);
    setError(null);
    const before = (read as { generatedAt?: string } | null)?.generatedAt || '';
    let receivedFreshRead = false;
    try {
      await wsClient.marketInterpret(target);
      for (let i = 0; i < 30 && alive.current; i += 1) {
        await sleep(3000);
        try {
          const next = await wsClient.marketReadGet(target);
          if (next && (next as { generatedAt?: string }).generatedAt !== before) {
            if (alive.current) setRead(next as T);
            receivedFreshRead = true;
            break;
          }
        } catch {
          /* transient — keep polling */
        }
      }
      if (!receivedFreshRead && alive.current)
        setError('No fresh model read arrived within 90 seconds. Try again after checking provider availability.');
    } catch (caught) {
      if (alive.current)
        setError(caught instanceof Error ? caught.message : 'The model read could not be started. Check provider availability and retry.');
    } finally {
      if (alive.current) setRunning(false);
    }
  }, [target, read]);

  return { read, loading, running, error, run, reload: () => setRetryKey((value) => value + 1) };
}
