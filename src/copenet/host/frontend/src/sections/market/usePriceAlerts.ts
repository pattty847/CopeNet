import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { PriceAlert } from './types';
import type { AlertRule } from './monitoring/types';
import { newAlert } from './monitoring/model';

export function projectPriceAlerts(rules: AlertRule[], symbol: string): PriceAlert[] {
  return rules.filter((rule) => rule.symbol === symbol && rule.enabled && rule.left.kind === 'price' && rule.right.kind === 'constant').map((rule) => ({ alertId: rule.alertId, symbol: rule.symbol, direction: rule.direction, threshold: rule.right.value! }));
}

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
      const next = await wsClient.marketMonitoring.alerts();
      if (reloadSequence.current === sequence) setAlerts(projectPriceAlerts(next.alerts, symbol));
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

  const create = async (direction: 'above' | 'below', threshold: number) => {
    setLoading(true);
    setError(null);
    try {
      const state = await wsClient.marketMonitoring.scans();
      const scan = state.scans.find((item) => item.id === 'morning' && item.sources.includes('prices') && item.resolvedSymbols.includes(symbol)) ?? state.scans.find((item) => item.sources.includes('prices') && item.resolvedSymbols.includes(symbol));
      if (!scan) throw new Error('Add this symbol to a price scan in Market → Scans & alerts first.');
      const rule = { ...newAlert(symbol), scanId: scan.id, direction, left: { kind: 'price' as const }, right: { kind: 'constant' as const, value: threshold } };
      const next = await wsClient.marketMonitoring.saveAlert(rule);
      setAlerts(projectPriceAlerts(next.alerts, symbol));
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
      setAlerts(projectPriceAlerts((await wsClient.marketMonitoring.cancelAlert(alertId)).alerts, symbol));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not cancel the price alert.');
    } finally {
      setLoading(false);
    }
  };

  return { alerts, loading, error, create, cancel, reload };
}
