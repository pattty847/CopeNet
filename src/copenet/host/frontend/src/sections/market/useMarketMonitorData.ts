// THE SEAM (blueprint §4) — now wired to the live market.* RPCs.
// Strategy: render instantly (illustrative sample, badged "preview"), kick a refresh, then poll
// market.dashboard.get until the store is populated and swap to the real payload. If the backend is
// offline the sample stays (honestly badged), so the UI never shows a blank screen.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { SAMPLE_DASHBOARD, SAMPLE_UNIVERSE, sampleTicker } from './sampleData';
import type { DashboardPayload, MarketRead, MorningBriefPayload, TickerDetailPayload, TickerEvidencePayload, TickerFundamentals, TickerRead, UniverseAsset, WatchlistItem } from './types';

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

/** Morning brief lane (overnight sentinel): load the stored brief; if it isn't today's yet,
 *  kick a sweep (idempotent server-side — the 7 AM sentinel and this auto-kick dedupe by date)
 *  and poll until today's brief lands. `onSwept` fires after a sweep completes so the caller
 *  can re-pull the dashboard the sweep just refreshed. */
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
      .then(async (next) => {
        if (!alive.current) return;
        if (next) setBrief(next);
        if (!next || next.briefDate !== localDateStamp()) {
          // Stale or missing — catch up now rather than waiting for tomorrow's 7 AM sweep.
          setGenerating(true);
          try {
            await wsClient.marketBriefRun(false);
            await pollUntilFresh(next?.generatedAt || '');
          } catch {
            /* backend offline — honest empty state stands */
          } finally {
            if (alive.current) setGenerating(false);
          }
        }
      })
      .catch(() => {
        /* backend offline — honest empty state stands */
      });
    return () => {
      alive.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

export interface TickerFundamentalsState {
  data: TickerFundamentals | null;
  loading: boolean;
  /** True once a load finished and the backend had no SEC fundamentals (ETFs, no-match filers). */
  unavailable: boolean;
  /** Lazy trigger — fetch on first overlay toggle, cached for the rest of the visit. */
  load: () => Promise<void>;
}

export function useTickerFundamentals(symbol: string): TickerFundamentalsState {
  const normalized = symbol.trim().toUpperCase();
  const [data, setData] = useState<TickerFundamentals | null>(null);
  const [loading, setLoading] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const loadedFor = useRef<string | null>(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    setData(null);
    setUnavailable(false);
    loadedFor.current = null;
    return () => {
      alive.current = false;
    };
  }, [normalized]);

  const load = useCallback(async () => {
    if (!normalized || loadedFor.current === normalized || loading) return;
    setLoading(true);
    try {
      const next = await wsClient.marketTickerFundamentals(normalized);
      if (!alive.current) return;
      loadedFor.current = normalized;
      setData(next);
      setUnavailable(next === null || !(next.revenueQuarterly?.length));
    } catch {
      /* backend offline — leave untouched so a later toggle retries */
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalized, loading]);

  return { data, loading, unavailable, load };
}

export interface TickerEvidenceState {
  payload: TickerEvidencePayload | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useTickerEvidence(symbol: string): TickerEvidenceState {
  const normalized = symbol.trim().toUpperCase();
  const [payload, setPayload] = useState<TickerEvidencePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latestSymbol = useRef(normalized);

  useEffect(() => {
    let alive = true;
    latestSymbol.current = normalized;
    setPayload(null);
    setError(null);
    setLoading(Boolean(normalized));
    if (!normalized) return () => {
      alive = false;
    };
    wsClient
      .marketTickerEvidence(normalized, false)
      .then((next) => {
        if (alive && latestSymbol.current === normalized) setPayload(next);
      })
      .catch((err) => {
        if (alive && latestSymbol.current === normalized) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (alive && latestSymbol.current === normalized) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [normalized]);

  const refresh = useCallback(async () => {
    if (!normalized) return;
    setRefreshing(true);
    setError(null);
    try {
      const next = await wsClient.marketTickerEvidence(normalized, true);
      if (latestSymbol.current === normalized) setPayload(next);
    } catch (err) {
      if (latestSymbol.current === normalized) setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (latestSymbol.current === normalized) setRefreshing(false);
    }
  }, [normalized]);

  return { payload, loading, refreshing, error, refresh };
}
