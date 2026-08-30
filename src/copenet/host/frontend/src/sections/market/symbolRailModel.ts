// The ordered set of symbols the rail traverses.
//
// Ticker analysis is a traversal, not a lookup: an operator moves between a bounded set of
// names for an hour. j/k only mean something if that set has an order, so the order is
// derived once here and shared by the rail's rendering and the workspace's keyboard.

import type { WatchlistItem } from './types';

export interface RailEntry {
  symbol: string;
  group: string;
  name?: string;
  change?: string;
  tone?: WatchlistItem['tone'];
  spark?: number[];
}

export function buildRailEntries({
  watchlist,
  recents,
  peers,
  current,
}: {
  watchlist: WatchlistItem[];
  recents: string[];
  peers: string[];
  current: string;
}): RailEntry[] {
  const seen = new Set<string>();
  const entries: RailEntry[] = [];

  const push = (entry: RailEntry) => {
    const symbol = entry.symbol.trim().toUpperCase();
    if (!symbol || seen.has(symbol)) return;
    seen.add(symbol);
    entries.push({ ...entry, symbol });
  };

  for (const item of watchlist) {
    push({ symbol: item.symbol, group: 'Watchlist', name: item.name, change: item.change, tone: item.tone, spark: item.spark });
  }

  // The current symbol always appears even when it is not on a list, because the rail is
  // also the "where am I" indicator and a highlight with no row is a dead end.
  push({ symbol: current, group: 'Recent' });
  for (const symbol of recents) push({ symbol, group: 'Recent' });

  // Comparison peers are already loaded and already on screen as chart lines; being able to
  // step onto one is free and is exactly what you want after seeing it diverge.
  for (const symbol of peers) push({ symbol, group: 'On chart' });

  return entries;
}

export function stepRail(entries: RailEntry[], current: string, delta: 1 | -1): string | null {
  if (!entries.length) return null;
  const index = entries.findIndex((entry) => entry.symbol === current.trim().toUpperCase());
  if (index === -1) return entries[0].symbol;
  const next = index + delta;
  if (next < 0 || next >= entries.length) return null;
  return entries[next].symbol;
}
