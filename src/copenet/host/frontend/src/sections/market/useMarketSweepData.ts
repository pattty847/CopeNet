// Stored Market snapshots load passively. Full scans require a schedule or an explicit action.
import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { SAMPLE_DASHBOARD } from './sampleData';
import type { DashboardPayload, MorningBriefPayload } from './types';

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** The durable store is populated once a refresh has computed real data (macro gets items / goes live). */
function isPopulated(d: DashboardPayload | null): boolean {
  if (!d) return false;
  return (d.macro?.data?.length ?? 0) > 0 || d.macro?.status === 'live';
}

export interface MarketDashboardState {
  dashboard: DashboardPayload;
  refreshing: boolean;
  live: boolean;
  refresh: () => Promise<void>;
  /** Re-pull the stored dashboard without triggering a new compute (used after server-side syncs). */
  reload: () => Promise<void>;
}

export function useMarketDashboard(): MarketDashboardState {
  const [dashboard, setDashboard] = useState<DashboardPayload>(SAMPLE_DASHBOARD);
  const [refreshing, setRefreshing] = useState(false);
  const [live, setLive] = useState(false);
  const cancelled = useRef(false);
  const lastAsOf = useRef<string>('');

  const refresh = useCallback(async () => {
    setRefreshing(true);
    const before = lastAsOf.current; // the backend stamps a new asOf per compute
    try {
      await wsClient.marketRefresh('all');
      for (let i = 0; i < 28 && !cancelled.current; i += 1) {
        await sleep(2500);
        try {
          const next = await wsClient.marketDashboard();
          if (isPopulated(next) && !cancelled.current) {
            setDashboard(next);
            setLive(true);
            lastAsOf.current = next.asOf;
            // stop once the fresh compute has landed (asOf advanced past pre-refresh value)
            if (next.asOf && next.asOf !== before) break;
          }
        } catch {
          /* keep polling — transient */
        }
      }
    } catch {
      /* backend offline — keep the illustrative sample (already badged preview) */
    } finally {
      if (!cancelled.current) setRefreshing(false);
    }
  }, []);

  const reload = useCallback(async () => {
    try {
      const next = await wsClient.marketDashboard();
      if (!cancelled.current && isPopulated(next)) {
        setDashboard(next);
        setLive(true);
        lastAsOf.current = next.asOf;
      }
    } catch {
      /* offline — keep what we have */
    }
  }, []);

  useEffect(() => {
    cancelled.current = false;
    // Opening Market is read-only, including an empty cache or an offline backend.
    void reload();
    return () => {
      cancelled.current = true;
    };
  }, [reload]);

  return { dashboard, refreshing, live, refresh, reload };
}

/** Local YYYY-MM-DD — matches the backend's operator-local briefDate stamp. */
function localDateStamp(): string {
  return new Date().toLocaleDateString('sv-SE');
}

export interface MorningBriefState {
  brief: MorningBriefPayload | null;
  /** True while a sweep we triggered is running server-side. */
  generating: boolean;
  /** Force a fresh sweep now (the operator's button). */
  runNow: () => Promise<void>;
}

/** Load the stored brief without scanning. Only Run now may start a sweep here. */
export function useMorningBrief(onSwept?: () => Promise<void>): MorningBriefState {
  const [brief, setBrief] = useState<MorningBriefPayload | null>(null);
  const [generating, setGenerating] = useState(false);
  const alive = useRef(true);

  const pollUntilFresh = useCallback(
    async (before: string) => {
      // A full sweep is ~40-70s for the whole watchlist; poll up to ~3 min.
      for (let i = 0; i < 36 && alive.current; i += 1) {
        await sleep(5000);
        try {
          const next = await wsClient.marketBriefGet();
          if (next && next.generatedAt !== before && next.briefDate === localDateStamp()) {
            if (alive.current) {
              setBrief(next);
              await onSwept?.();
            }
            return;
          }
        } catch {
          /* transient — keep polling */
        }
      }
    },
    [onSwept],
  );

  useEffect(() => {
    alive.current = true;
    wsClient
      .marketBriefGet()
      .then((next) => {
        if (alive.current && next) setBrief(next);
      })
      .catch(() => {
        /* backend offline — honest empty state stands */
      });
    return () => {
      alive.current = false;
    };
  }, []);

  const runNow = useCallback(async () => {
    setGenerating(true);
    try {
      await wsClient.marketBriefRun(true);
      await pollUntilFresh(brief?.generatedAt || '');
    } catch {
      /* backend offline */
    } finally {
      if (alive.current) setGenerating(false);
    }
  }, [brief, pollUntilFresh]);

  return { brief, generating, runNow };
}
