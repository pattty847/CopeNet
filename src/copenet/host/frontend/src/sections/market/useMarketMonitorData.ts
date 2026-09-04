// Market research, watchlist and model-read hooks over the live market.* RPCs.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import type { TradeLedger } from '../../lib/wsMarketRpc';
import { useModelRead } from './useModelRead';
import type { LedgerReport, MarketRead, MarketSession, TickerDetailPayload, TickerEvidencePayload, TickerFundamentals, TickerRead, WatchlistItem } from './types';


export function useMarketRead() {
  return useModelRead<MarketRead>('market');
}

/** The day-over-day trail behind the briefing. Fetched once — it only changes on a sweep,
 *  and the briefing overlay is the only thing that reads it. */
export function useMarketSessions() {
  const [sessions, setSessions] = useState<MarketSession[]>([]);
  useEffect(() => {
    let alive = true;
    wsClient
      .marketSessionsGet()
      .then((next) => {
        if (alive) setSessions(next);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  return sessions;
}

export function useTickerRead(symbol: string) {
  return useModelRead<TickerRead>(symbol);
}

/** Enough claims for the Ledger section to show outcomes by week, not just the last few days. */
const LEDGER_RECENT_CLAIMS = 400;

export function useForwardLedger(): { report: LedgerReport | null; loading: boolean } {
  const [report, setReport] = useState<LedgerReport | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    wsClient
      .marketLedgerGet(LEDGER_RECENT_CLAIMS)
      .then((next) => {
        if (alive) setReport(next);
      })
      .catch(() => {
        /* backend offline — panel shows its empty state */
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  return { report, loading };
}

export interface MarketWatchlistState {
  items: WatchlistItem[];
  lists: string[];
  active: string;
  loading: boolean;
  symbols: Set<string>;
  add: (symbol: string, name?: string) => Promise<void>;
  remove: (symbol: string) => Promise<void>;
  createList: (name: string) => Promise<void>;
  deleteList: (name: string) => Promise<void>;
  selectList: (name: string) => Promise<void>;
  importFromWebull: () => Promise<void>;
  importing: boolean;
}

export function useMarketWatchlist(): MarketWatchlistState {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [lists, setLists] = useState<string[]>(['Default']);
  const [active, setActive] = useState('Default');
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);
  const alive = useRef(true);

  const apply = useCallback((state: { items: WatchlistItem[]; lists: string[]; active: string }) => {
    if (!alive.current) return;
    setItems(state.items);
    setLists(state.lists);
    setActive(state.active);
  }, []);

  useEffect(() => {
    alive.current = true;
    wsClient
      .marketWatchlistGet()
      .then(apply)
      .catch(() => {
        /* backend offline — watchlist just stays empty until it's reachable */
      })
      .finally(() => {
        if (alive.current) setLoading(false);
      });
    return () => {
      alive.current = false;
    };
  }, [apply]);

  const add = useCallback(async (symbol: string, name = '') => {
    apply(await wsClient.marketWatchlistAdd(symbol, name));
  }, [apply]);

  const remove = useCallback(async (symbol: string) => {
    apply(await wsClient.marketWatchlistRemove(symbol));
  }, [apply]);

  const createList = useCallback(async (name: string) => {
    apply(await wsClient.marketWatchlistListCreate(name));
  }, [apply]);

  const deleteList = useCallback(async (name: string) => {
    apply(await wsClient.marketWatchlistListDelete(name));
  }, [apply]);

  const selectList = useCallback(async (name: string) => {
    setLoading(true);
    try {
      apply(await wsClient.marketWatchlistListSelect(name));
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [apply]);

  /** Pull the operator's Webull lists again — a one-shot import, not a live subscription, so
   * edits made in the Webull app land here only when this runs. */
  const importFromWebull = useCallback(async () => {
    setImporting(true);
    try {
      await wsClient.marketWebullWatchlistsImport();
      apply(await wsClient.marketWatchlistGet());
    } finally {
      if (alive.current) setImporting(false);
    }
  }, [apply]);

  const symbols = useMemo(() => new Set(items.map((item) => item.symbol)), [items]);

  return { items, lists, active, loading, symbols, add, remove, createList, deleteList, selectList, importFromWebull, importing };
}

export interface TradeLedgerState {
  ledger: TradeLedger | null;
  loading: boolean;
  syncing: boolean;
  error: string | null;
  sync: () => Promise<void>;
}

/** One ledger fetch shared by the P&L panel and the trade-history panel — two RPC calls would let
 *  the two views drift apart after a fill sync. */
export function useTradeLedger(): TradeLedgerState {
  const [ledger, setLedger] = useState<TradeLedger | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    wsClient
      .marketWebullPnlGet()
      .then((next) => {
        if (alive) setLedger(next);
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : 'could not load the ledger');
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const sync = useCallback(async () => {
    setSyncing(true);
    setError(null);
    try {
      setLedger(await wsClient.marketWebullOrdersSync());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'fill history sync failed');
    } finally {
      setSyncing(false);
    }
  }, []);

  return { ledger, loading, syncing, error, sync };
}

export interface TickerDetailState {
  detail: TickerDetailPayload | null;
  loading: boolean;
  error: string | null;
  /** True while `detail` belongs to a previous symbol or fetch. The workspace keeps the frame
   *  painted and marks the pending symbol rather than blanking — a fixed-frame layout that
   *  empties on every switch reads as a crash. */
  stale: boolean;
  reload: () => Promise<void>;
}

/** Small LRU of recent payloads. Ticker analysis is a traversal — an operator moves back and
 *  forth between the same handful of names for an hour — so the second visit should be
 *  instant instead of a fresh round trip. */
const DETAIL_CACHE = new Map<string, TickerDetailPayload>();
const DETAIL_CACHE_LIMIT = 20;

function cacheDetail(symbol: string, payload: TickerDetailPayload): void {
  DETAIL_CACHE.delete(symbol);
  DETAIL_CACHE.set(symbol, payload);
  while (DETAIL_CACHE.size > DETAIL_CACHE_LIMIT) {
    const oldest = DETAIL_CACHE.keys().next().value;
    if (oldest === undefined) break;
    DETAIL_CACHE.delete(oldest);
  }
}

export function useTickerDetail(symbol: string): TickerDetailState {
  const normalized = symbol.trim().toUpperCase();
  // Keyed by the symbol that was ASKED FOR, never by the payload's own `symbol`. The backend
  // canonicalises (BRK.B -> BRK-B, aliases, suffixes), so comparing against the response
  // would mark a perfectly fresh payload stale forever.
  const [entry, setEntry] = useState<{ requested: string; payload: TickerDetailPayload } | null>(
    () => { const cached = DETAIL_CACHE.get(normalized); return cached ? { requested: normalized, payload: cached } : null; },
  );
  const [loading, setLoading] = useState(Boolean(normalized));
  const [error, setError] = useState<string | null>(null);
  const requestVersion = useRef(0);

  const reload = useCallback(async () => {
    if (!normalized) return;
    const version = ++requestVersion.current;
    setLoading(true);
    setError(null);
    try {
      const next = await wsClient.marketTicker(normalized);
      cacheDetail(normalized, next);
      if (requestVersion.current === version) setEntry({ requested: normalized, payload: next });
    } catch (err) {
      if (requestVersion.current === version) {
        setEntry(null);
        setError(err instanceof Error ? err.message : 'Ticker data is unavailable.');
      }
    } finally {
      if (requestVersion.current === version) setLoading(false);
    }
  }, [normalized]);

  useEffect(() => {
    const cached = DETAIL_CACHE.get(normalized);
    if (cached) setEntry({ requested: normalized, payload: cached });
    void reload();
    return () => {
      requestVersion.current += 1;
    };
  }, [normalized, reload]);

  return {
    detail: entry?.payload ?? null,
    loading,
    error,
    stale: entry != null && entry.requested !== normalized,
    reload,
  };
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
      setUnavailable(next === null || (!next.revenueQuarterly?.length && !next.revenueAnnual?.length));
    } catch {
      // Mark the attempt as spent. Leaving it unset re-armed the caller's effect on the next
      // render, which turned an offline backend into an unthrottled request loop.
      loadedFor.current = normalized;
    } finally {
      if (alive.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [normalized]);

  return { data, loading, unavailable, load };
}

/** SEC history depth presets for the ticker page — days of Form 4/144/8-K history. */
export const SEC_DEPTHS = [
  { label: '6M', days: 180 },
  { label: '2Y', days: 730 },
  { label: '5Y', days: 1825 },
] as const;

export interface TickerEvidenceState {
  payload: TickerEvidencePayload | null;
  loading: boolean;
  refreshing: boolean;
  error: string | null;
  depthDays: number;
  setDepthDays: (days: number) => void;
  refresh: () => Promise<void>;
}

export function useTickerEvidence(symbol: string): TickerEvidenceState {
  const normalized = symbol.trim().toUpperCase();
  const [payload, setPayload] = useState<TickerEvidencePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [depthDays, setDepthDays] = useState<number>(180);
  const latestKey = useRef(`${normalized}:180`);

  useEffect(() => {
    let alive = true;
    const key = `${normalized}:${depthDays}`;
    latestKey.current = key;
    setPayload(null);
    setError(null);
    setLoading(Boolean(normalized));
    if (!normalized) return () => {
      alive = false;
    };
    wsClient
      .marketTickerEvidence(normalized, false, depthDays)
      .then((next) => {
        if (alive && latestKey.current === key) setPayload(next);
      })
      .catch((err) => {
        if (alive && latestKey.current === key) {
          const message = err instanceof Error ? err.message : String(err);
          // Deep first pulls can outlive the RPC timeout while the server keeps caching —
          // an immediate retry usually lands on the cache.
          setError(/timed?\s?out/i.test(message) ? 'Deep SEC pull is still caching server-side — try again in ~30s.' : message);
        }
      })
      .finally(() => {
        if (alive && latestKey.current === key) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [normalized, depthDays]);

  const refresh = useCallback(async () => {
    if (!normalized) return;
    const key = `${normalized}:${depthDays}`;
    setRefreshing(true);
    setError(null);
    try {
      const next = await wsClient.marketTickerEvidence(normalized, true, depthDays);
      if (latestKey.current === key) setPayload(next);
    } catch (err) {
      if (latestKey.current === key) {
        const message = err instanceof Error ? err.message : String(err);
        setError(/timed?\s?out/i.test(message) ? 'Deep SEC pull is still caching server-side — try again in ~30s.' : message);
      }
    } finally {
      if (latestKey.current === key) setRefreshing(false);
    }
  }, [normalized, depthDays]);

  return { payload, loading, refreshing, error, depthDays, setDepthDays, refresh };
}
