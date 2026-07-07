// THE SEAM (blueprint §4) — now wired to the live market.* RPCs.
// Strategy: render instantly (illustrative sample, badged "preview"), kick a refresh, then poll
// market.dashboard.get until the store is populated and swap to the real payload. If the backend is
// offline the sample stays (honestly badged), so the UI never shows a blank screen.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { SAMPLE_DASHBOARD, SAMPLE_UNIVERSE, sampleTicker } from './sampleData';
import type { DashboardPayload, MarketRead, TickerDetailPayload, TickerRead, UniverseAsset, WatchlistItem } from './types';

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
    // Show the stored snapshot instantly. Only auto-compute when the store is empty — otherwise a
    // full refresh (~40s for the whole watchlist) would run on every visit. Refresh is on-demand.
    wsClient
      .marketDashboard()
      .then((next) => {
        if (cancelled.current) return;
        if (isPopulated(next)) {
          setDashboard(next);
          setLive(true);
          lastAsOf.current = next.asOf;
        } else {
          void refresh();
        }
      })
      .catch(() => {
        if (!cancelled.current) void refresh();
      });
    return () => {
      cancelled.current = true;
    };
  }, [refresh]);

  return { dashboard, refreshing, live, refresh, reload };
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

/** Generic model-read lane (Insight Engine Phase D): load the stored read, and expose a
 *  trigger that kicks market.interpret then polls market.read.get until a FRESH read lands
 *  (generatedAt advances). The model call runs server-side in the background. */
function useModelRead<T extends MarketRead | TickerRead>(target: string) {
  const [read, setRead] = useState<T | null>(null);
  const [running, setRunning] = useState(false);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    setRead(null);
    wsClient
      .marketReadGet(target)
      .then((next) => {
        if (alive.current && next) setRead(next as T);
      })
      .catch(() => {});
    return () => {
      alive.current = false;
    };
  }, [target]);

  const run = useCallback(async () => {
    setRunning(true);
    const before = (read as { generatedAt?: string } | null)?.generatedAt || '';
    try {
      await wsClient.marketInterpret(target);
      for (let i = 0; i < 30 && alive.current; i += 1) {
        await sleep(3000);
        try {
          const next = await wsClient.marketReadGet(target);
          if (next && (next as { generatedAt?: string }).generatedAt !== before) {
            if (alive.current) setRead(next as T);
            break;
          }
        } catch {
          /* transient — keep polling */
        }
      }
    } catch {
      /* provider unavailable — leave the read as-is */
    } finally {
      if (alive.current) setRunning(false);
    }
  }, [target, read]);

  return { read, running, run };
}

export function useMarketRead() {
  return useModelRead<MarketRead>('market');
}

export function useTickerRead(symbol: string) {
  return useModelRead<TickerRead>(symbol);
}

export interface MarketWatchlistState {
  items: WatchlistItem[];
  loading: boolean;
  symbols: Set<string>;
  add: (symbol: string, name?: string) => Promise<void>;
  remove: (symbol: string) => Promise<void>;
}

export function useMarketWatchlist(): MarketWatchlistState {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    wsClient
      .marketWatchlistGet()
      .then((next) => {
        if (alive.current) setItems(next);
      })
      .catch(() => {
        /* backend offline — watchlist just stays empty until it's reachable */
      })
      .finally(() => {
        if (alive.current) setLoading(false);
      });
    return () => {
      alive.current = false;
    };
  }, []);

  const add = useCallback(async (symbol: string, name = '') => {
    const next = await wsClient.marketWatchlistAdd(symbol, name);
    if (alive.current) setItems(next);
  }, []);

  const remove = useCallback(async (symbol: string) => {
    const next = await wsClient.marketWatchlistRemove(symbol);
    if (alive.current) setItems(next);
  }, []);

  const symbols = useMemo(() => new Set(items.map((item) => item.symbol)), [items]);

  return { items, loading, symbols, add, remove };
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
