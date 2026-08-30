// Persisted workspace preferences for the ticker frame.
//
// Two scopes, deliberately separated. WORKSPACE-STICKY state describes how the operator
// likes to look at any asset — interval, range, log axis, which research tab, how tall the
// drawer is. SYMBOL-SCOPED state describes one asset — comparisons and fundamental overlays
// — and must reset on switch. The baseline carried a comparison into the next ticker and
// rewrote the URL as if the operator had asked for it, which is the bug this split prevents.

export type ResearchTab = 'overview' | 'fundamentals' | 'evidence' | 'synthesis';
export type DrawerSnap = 'collapsed' | 'half' | 'full';
export type DrawerSizes = Partial<Record<ResearchTab, number>>;

export const DRAWER_MIN_PERCENT = 22;
export const DRAWER_MAX_PERCENT = 78;

export const RESEARCH_TABS: { id: ResearchTab; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'fundamentals', label: 'Fundamentals' },
  { id: 'evidence', label: 'SEC & Events' },
  { id: 'synthesis', label: 'Synthesis' },
];

const SNAP_ORDER: DrawerSnap[] = ['collapsed', 'half', 'full'];

export function nextSnap(snap: DrawerSnap): DrawerSnap {
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

const TAB_KEY = 'mm-tw-tab';
const SNAP_KEY = 'mm-tw-snap';
const RAIL_KEY = 'mm-tw-rail';
const LOG_KEY = 'mm-log-scale';
const DRAWER_SIZE_KEY = 'mm-tw-drawer-size';

function isTab(value: string | null): value is ResearchTab {
  return value != null && RESEARCH_TABS.some((tab) => tab.id === value);
}

export function loadTab(): ResearchTab {
  const stored = read(TAB_KEY);
  return isTab(stored) ? stored : 'overview';
}

export function saveTab(tab: ResearchTab): void {
  write(TAB_KEY, tab);
}

/** Drawer height is remembered PER TAB. Fundamentals small multiples need room that
 *  Overview would only waste, so one global height is wrong for at least one of them. */
export function loadSnaps(): Record<ResearchTab, DrawerSnap> {
  // Defaults per tab, because the content genuinely differs in size: the financial explorer
  // and the SEC activity chart are charts and need height; Overview reads fine at half.
  const fallback = RESEARCH_TABS.reduce(
    (acc, tab) => ({ ...acc, [tab.id]: tab.id === 'fundamentals' || tab.id === 'evidence' ? 'full' : 'half' }),
    {} as Record<ResearchTab, DrawerSnap>,
  );
  const raw = read(SNAP_KEY);
  if (!raw) return fallback;
  try {
    const parsed = JSON.parse(raw) as Partial<Record<ResearchTab, DrawerSnap>>;
    for (const tab of RESEARCH_TABS) {
      const value = parsed[tab.id];
      if (value && SNAP_ORDER.includes(value)) fallback[tab.id] = value;
    }
  } catch {
    /* corrupt preference — fall back rather than throw the workspace away */
  }
  return fallback;
}

export function saveSnaps(snaps: Record<ResearchTab, DrawerSnap>): void {
  write(SNAP_KEY, JSON.stringify(snaps));
}

export function clampDrawerSize(value: number): number {
  return Math.min(DRAWER_MAX_PERCENT, Math.max(DRAWER_MIN_PERCENT, value));
}

/** A manual height is remembered per tab for the same reason as its snap preset: the SEC
 *  timeline and a compact overview have different useful working heights. */
export function loadDrawerSizes(): DrawerSizes {
  const raw = read(DRAWER_SIZE_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return RESEARCH_TABS.reduce<DrawerSizes>((sizes, tab) => {
      const value = parsed[tab.id];
      if (typeof value === 'number' && Number.isFinite(value)) sizes[tab.id] = clampDrawerSize(value);
      return sizes;
    }, {});
  } catch {
    return {};
  }
}

export function saveDrawerSizes(sizes: DrawerSizes): void {
  write(DRAWER_SIZE_KEY, JSON.stringify(sizes));
}

export function loadRailCollapsed(): boolean {
  return read(RAIL_KEY) === '1';
}

export function saveRailCollapsed(collapsed: boolean): void {
  write(RAIL_KEY, collapsed ? '1' : '0');
}

export function loadLogScale(): boolean {
  return read(LOG_KEY) === '1';
}

export function saveLogScale(enabled: boolean): void {
  write(LOG_KEY, enabled ? '1' : '0');
}

/** Symbols the operator has opened this session, newest first, current symbol excluded.
 *  Session-scoped on purpose: "recently viewed" that survives a week is just a stale list. */
export function pushRecent(symbol: string, recents: string[], limit = 8): string[] {
  const next = [symbol, ...recents.filter((item) => item !== symbol)];
  return next.slice(0, limit);
}
