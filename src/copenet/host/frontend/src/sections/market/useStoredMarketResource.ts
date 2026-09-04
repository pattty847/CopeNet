import { useCallback, useEffect, useRef, useState } from 'react';

/** Read-only workspace acquisition. Null is a valid result, never a demo fallback. */
export function useStoredMarketResource<T>(fetcher: () => Promise<T>) {
  const [data, setData] = useState<T | null>(null);
  const [settled, setSettled] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const generation = useRef(0);
  const inFlight = useRef<Promise<void> | null>(null);

  const reload = useCallback((): Promise<void> => {
    if (inFlight.current) return inFlight.current;
    const version = generation.current;
    setLoading(true);
    const request = fetcher()
      .then((next) => {
        if (version !== generation.current) return;
        setData(next);
        setError(null);
      })
      .catch((reason) => {
        if (version === generation.current) setError(reason instanceof Error ? reason.message : 'Could not load saved market data.');
      })
      .finally(() => {
        if (version !== generation.current) return;
        inFlight.current = null;
        setSettled(true);
        setLoading(false);
      });
    inFlight.current = request;
    return request;
  }, [fetcher]);

  useEffect(() => {
    void reload();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void reload();
    }, 30_000);
    return () => {
      generation.current += 1;
      inFlight.current = null;
      window.clearInterval(timer);
    };
  }, [reload]);

  return { data, settled, loading, error, reload };
}
