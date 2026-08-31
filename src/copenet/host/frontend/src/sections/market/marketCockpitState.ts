// Persisted preferences for the market cockpit frame.
//
// Mirrors tickerWorkspaceState's split on the market level: how the operator likes to look
// at THE MARKET — which dock tab, how tall the dock is per tab, whether the watch rail is
// collapsed — is sticky across visits. Nothing here is data; losing it costs a keypress.

export type MarketDockTab =
  | 'rotation'
  | 'rates'
  | 'portfolio'
  | 'evidence'
  | 'signals'
  | 'ledger'
  | 'backtest';

export type DockSnap = 'collapsed' | 'half' | 'full';

export const MARKET_DOCK_TABS: { id: MarketDockTab; label: string }[] = [
  { id: 'rotation', label: 'Rotation' },
  { id: 'rates', label: 'Rates' },
  { id: 'portfolio', label: 'Portfolio' },
  { id: 'evidence', label: 'Evidence' },
  { id: 'signals', label: 'Signals' },
  { id: 'ledger', label: 'Ledger' },
  { id: 'backtest', label: 'Backtest' },
];

const SNAP_ORDER: DockSnap[] = ['collapsed', 'half', 'full'];

export function nextDockSnap(snap: DockSnap): DockSnap {
  return SNAP_ORDER[(SNAP_ORDER.indexOf(snap) + 1) % SNAP_ORDER.length];
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* private mode — preferences are a convenience, never a requirement */
  }
}

const TAB_KEY = 'mm-mc-tab';
const SNAP_KEY = 'mm-mc-snap';
const RAIL_KEY = 'mm-mc-rail';
const SIZE_KEY = 'mm-mc-dock-size';

function isTab(value: string | null): value is MarketDockTab {
  return value != null && MARKET_DOCK_TABS.some((tab) => tab.id === value);
}

export function loadDockTab(): MarketDockTab {
  const stored = read(TAB_KEY);
  return isTab(stored) ? stored : 'rotation';
}

export function saveDockTab(tab: MarketDockTab): void {
  write(TAB_KEY, tab);
}

/** Dock height is remembered per tab: the RRG and the backtest lab are charts and earn
 *  height; the ledger reads fine at half. The dock starts collapsed — orientation owns the
 *  stage until the operator asks to investigate. */
export function loadDockSnaps(): Record<MarketDockTab, DockSnap> {
  const fallback = MARKET_DOCK_TABS.reduce(
    (acc, tab) => ({
      ...acc,
      [tab.id]: tab.id === 'rotation' || tab.id === 'rates' || tab.id === 'backtest' ? 'full' : 'half',
    }),
    {} as Record<MarketDockTab, DockSnap>,
  );
  const raw = read(SNAP_KEY);
  if (!raw) return fallback;
  try {
    const parsed = JSON.parse(raw) as Partial<Record<MarketDockTab, DockSnap>>;
    for (const tab of MARKET_DOCK_TABS) {
      const value = parsed[tab.id];
      if (value && SNAP_ORDER.includes(value)) fallback[tab.id] = value;
    }
  } catch {
    /* corrupt preference — fall back rather than throw the cockpit away */
  }
  return fallback;
}

export function saveDockSnaps(snaps: Record<MarketDockTab, DockSnap>): void {
  write(SNAP_KEY, JSON.stringify(snaps));
}

export type DockSizes = Partial<Record<MarketDockTab, number>>;

export function loadDockSizes(clamp: (value: number) => number): DockSizes {
  const raw = read(SIZE_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return MARKET_DOCK_TABS.reduce<DockSizes>((sizes, tab) => {
      const value = parsed[tab.id];
      if (typeof value === 'number' && Number.isFinite(value)) sizes[tab.id] = clamp(value);
      return sizes;
    }, {});
  } catch {
    return {};
  }
}

export function saveDockSizes(sizes: DockSizes): void {
  write(SIZE_KEY, JSON.stringify(sizes));
}

export function loadCockpitRailCollapsed(): boolean {
  return read(RAIL_KEY) === '1';
}

export function saveCockpitRailCollapsed(collapsed: boolean): void {
  write(RAIL_KEY, collapsed ? '1' : '0');
}
