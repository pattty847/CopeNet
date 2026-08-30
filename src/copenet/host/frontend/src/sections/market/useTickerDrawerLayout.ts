import { useCallback, useEffect, useState } from 'react';
import {
  loadDrawerSizes,
  loadSnaps,
  nextSnap,
  saveDrawerSizes,
  saveSnaps,
  type DrawerSnap,
  type ResearchTab,
} from './tickerWorkspaceState';

export function useTickerDrawerLayout(tab: ResearchTab) {
  const [snaps, setSnaps] = useState(loadSnaps);
  const [sizes, setSizes] = useState(loadDrawerSizes);

  useEffect(() => saveSnaps(snaps), [snaps]);
  useEffect(() => saveDrawerSizes(sizes), [sizes]);

  const snap = snaps[tab] ?? 'half';
  const size = sizes[tab];
  const setSnap = useCallback(
    (next: DrawerSnap) => setSnaps((current) => ({ ...current, [tab]: next })),
    [tab],
  );
  const resize = useCallback(
    (next: number) => setSizes((current) => ({ ...current, [tab]: next })),
    [tab],
  );
  const ensureOpen = useCallback((target: ResearchTab) => {
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
    setSnap(nextSnap(snap));
  }, [setSnap, snap, tab]);

  return { snap, size, setSnap, resize, ensureOpen, cycleSnap };
}
