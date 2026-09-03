import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import type { AlertsState, IndicatorOption, NotificationsState, ScansState } from './types';

export function useMonitoring() {
  const [scans, setScans] = useState<ScansState | null>(null);
  const [alerts, setAlerts] = useState<AlertsState | null>(null);
  const [catalogue, setCatalogue] = useState<IndicatorOption[]>([]);
  const [notifications, setNotifications] = useState<NotificationsState | null>(null);
  const [error, setError] = useState('');
  const alive = useRef(true);
  const sequence = useRef(0);
  const reload = useCallback(async () => {
    const current = ++sequence.current;
    const api = wsClient.marketMonitoring;
    const results = await Promise.allSettled([api.scans(), api.alerts(), api.catalogue(), api.notifications()] as const);
    if (!alive.current || current !== sequence.current) return;
    if (results[0].status === 'fulfilled') setScans(results[0].value);
    if (results[1].status === 'fulfilled') setAlerts(results[1].value);
    if (results[2].status === 'fulfilled') setCatalogue(results[2].value.indicators);
    if (results[3].status === 'fulfilled') setNotifications(results[3].value);
    const failures = results
      .filter((result) => result.status === 'rejected')
      .map((result) => String(result.reason instanceof Error ? result.reason.message : result.reason));
    if (results[2].status === 'fulfilled' && results[2].value.error) failures.push(results[2].value.error);
    setError(failures.join(' · '));
  }, []);
  useEffect(() => {
    alive.current = true;
    void reload();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void reload();
    }, 15000);
    return () => {
      alive.current = false;
      window.clearInterval(timer);
    };
  }, [reload]);
  return { scans, alerts, catalogue, notifications, error, reload };
}
