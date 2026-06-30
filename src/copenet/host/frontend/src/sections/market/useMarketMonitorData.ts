// THE SEAM (blueprint §4) — now wired to the live market.* RPCs.
// Strategy: render instantly (illustrative sample, badged "preview"), kick a refresh, then poll
// market.dashboard.get until the store is populated and swap to the real payload. If the backend is
// offline the sample stays (honestly badged), so the UI never shows a blank screen.

import { useCallback, useEffect, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { SAMPLE_DASHBOARD, SAMPLE_UNIVERSE, sampleTicker } from './sampleData';
import type { DashboardPayload, TickerDetailPayload, UniverseAsset } from './types';

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
      for (let i = 0; i < 16 && !cancelled.current; i += 1) {
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

  useEffect(() => {
    cancelled.current = false;
    // 1) instant read of whatever is already stored (only swap in if it's real data)
    wsClient
      .marketDashboard()
      .then((next) => {
        if (!cancelled.current && isPopulated(next)) {
          setDashboard(next);
          setLive(true);
          lastAsOf.current = next.asOf;
        }
      })
      .catch(() => {});
    // 2) kick a fresh compute and poll it in
    void refresh();
    return () => {
      cancelled.current = true;
    };
  }, [refresh]);

  return { dashboard, refreshing, live, refresh };
}

export function useMarketUniverse(): UniverseAsset[] {
  const [universe, setUniverse] = useState<UniverseAsset[]>(SAMPLE_UNIVERSE);
  useEffect(() => {
    let alive = true;
    wsClient
      .marketUniverse()
      .then((next) => {
        if (alive && next && next.length) setUniverse(next);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  return universe;
}

export function useTickerDetail(symbol: string): TickerDetailPayload {
  const [detail, setDetail] = useState<TickerDetailPayload>(() => sampleTicker(symbol));
  useEffect(() => {
    let alive = true;
    setDetail(sampleTicker(symbol));
    wsClient
      .marketTicker(symbol)
      .then((next) => {
        if (alive && next) setDetail(next);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [symbol]);
  return detail;
}
