import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { PriceAlert } from './types';

export function usePriceAlerts(symbol: string) {
  const [alerts, setAlerts] = useState<PriceAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const reloadSequence = useRef(0);

  const reload = useCallback(async () => {
    const sequence = reloadSequence.current + 1;
    reloadSequence.current = sequence;
    setLoading(true);
    setError(null);
    setAlerts([]);
    try {
      const next = await wsClient.marketAlertsList(symbol);
      if (reloadSequence.current === sequence) setAlerts(next);
    } catch (reason) {
      if (reloadSequence.current === sequence) {
        setError(reason instanceof Error ? reason.message : 'Could not load price alerts.');
      }
    } finally {
      if (reloadSequence.current === sequence) setLoading(false);
    }
  }, [symbol]);

  useEffect(() => {
    void reload();
    return () => {
      reloadSequence.current += 1;
    };
  }, [reload]);

  const create = async (direction: 'above' | 'below', threshold: number, referencePrice: number) => {
    setLoading(true);
    setError(null);
    try {
      const next = await wsClient.marketAlertsCreate({ symbol, direction, threshold, referencePrice });
      setAlerts(next);
      return true;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not create the price alert.');
      return false;
    } finally {
      setLoading(false);
    }
  };

  const cancel = async (alertId: string) => {
    setLoading(true);
    setError(null);
    try {
      setAlerts(await wsClient.marketAlertsCancel(alertId, symbol));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not cancel the price alert.');
    } finally {
      setLoading(false);
    }
  };

  return { alerts, loading, error, create, cancel, reload };
}
