// Dashboard/brief readers never acquire data. Scans owns every broad-market run.
import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { SAMPLE_DASHBOARD } from './sampleData';
import type { DashboardPayload, MorningBriefPayload } from './types';

export function useMarketDashboard() {
  const [dashboard, setDashboard] = useState<DashboardPayload>(SAMPLE_DASHBOARD);
  const [live, setLive] = useState(false);
  const alive = useRef(true);
  const reload = useCallback(async () => {
    try {
      const next = await wsClient.marketDashboard();
      if (alive.current && ((next.macro?.data?.length ?? 0) > 0 || next.macro?.status === 'live')) {
        setDashboard(next); setLive(true);
      }
    } catch { /* Preserve the last snapshot; initial samples remain explicitly badged. */ }
  }, []);
  useEffect(() => {
    alive.current = true;
    void reload();
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void reload(); }, 30000);
    return () => { alive.current = false; window.clearInterval(timer); };
  }, [reload]);
  return { dashboard, live, reload };
}

export function useMorningBrief(onSwept?: () => Promise<void>) {
  const [brief, setBrief] = useState<MorningBriefPayload | null>(null);
  const previous = useRef('');
  useEffect(() => {
    let alive = true;
    const load = async () => {
      try {
        const next = await wsClient.marketBriefGet();
        if (!alive) return;
        setBrief(next);
        if (next && next.generatedAt !== previous.current) {
          previous.current = next.generatedAt;
          await onSwept?.();
        }
      } catch { /* Empty/stale state stands; no fallback scan. */ }
    };
    void load();
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void load(); }, 30000);
    return () => { alive = false; window.clearInterval(timer); };
  }, [onSwept]);
  return { brief };
}
