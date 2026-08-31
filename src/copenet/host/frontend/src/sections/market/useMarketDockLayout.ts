import { useCallback, useEffect, useState } from 'react';
import { clampDrawerSize } from './tickerWorkspaceState';
import {
  loadDockSizes,
  loadDockSnaps,
  loadDockTab,
  nextDockSnap,
  saveDockSizes,
  saveDockSnaps,
  saveDockTab,
  type DockSnap,
  type MarketDockTab,
} from './marketCockpitState';

/** Dock tab + per-tab snap/height for the market cockpit — the cockpit-side twin of
 *  useTickerDrawerLayout, persisted under its own keys. */
export function useMarketDockLayout() {
  const [tab, setTab] = useState<MarketDockTab>(loadDockTab);
  const [snaps, setSnaps] = useState(loadDockSnaps);
  const [sizes, setSizes] = useState(() => loadDockSizes(clampDrawerSize));

  useEffect(() => saveDockTab(tab), [tab]);
  useEffect(() => saveDockSnaps(snaps), [snaps]);
  useEffect(() => saveDockSizes(sizes), [sizes]);

  const snap = snaps[tab] ?? 'half';
  const size = sizes[tab];

  const setSnap = useCallback(
    (next: DockSnap) => setSnaps((current) => ({ ...current, [tab]: next })),
    [tab],
  );

  const resize = useCallback(
    (next: number) => setSizes((current) => ({ ...current, [tab]: clampDrawerSize(next) })),
    [tab],
  );

  /** Select a tab AND make sure the dock is open — a click on "Rotation →" that lands on a
   *  collapsed dock would otherwise change nothing visible. */
  const openTab = useCallback((target: MarketDockTab) => {
    setTab(target);
    setSnaps((current) => ({
      ...current,
      [target]: current[target] === 'collapsed' ? 'half' : current[target],
    }));
  }, []);

  const cycleSnap = useCallback(() => {
    setSizes((current) => {
      const next = { ...current };
      delete next[tab];
      return next;
    });
    setSnap(nextDockSnap(snap));
  }, [setSnap, snap, tab]);

  return { tab, snap, size, setTab, openTab, setSnap, resize, cycleSnap };
}
