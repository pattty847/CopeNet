// Persisted workspace preferences for the ticker frame.
//
// Two scopes, deliberately separated. WORKSPACE-STICKY state describes how the operator
// likes to look at any asset — interval, range, log axis, which research tab, how tall the
// drawer is. SYMBOL-SCOPED state describes one asset — comparisons and fundamental overlays
// — and must reset on switch. The baseline carried a comparison into the next ticker and
// rewrote the URL as if the operator had asked for it, which is the bug this split prevents.

import type { CandleStyle } from './heikinAshi';
import { INTRADAY_TIMEFRAMES, type ChartTimeframe } from './chartRanges';
import { loadRailPreference, railCollapsed, saveRailPreference } from './marketWorkstationState';

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
const LOG_KEY = 'mm-log-scale';
const CANDLE_STYLE_KEY = 'mm-candle-style';
const PINNED_TIMEFRAMES_KEY = 'mm-tw-pinned-timeframes';
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

/** The rail is one instrument across the market and ticker pages, so its state is one
 *  preference: the workstation's width rule decides until the operator chooses. */
export function loadRailCollapsed(): boolean {
  return railCollapsed(loadRailPreference(), typeof window === 'undefined' ? 1440 : window.innerWidth);
}

export function saveRailCollapsed(collapsed: boolean): void {
  saveRailPreference(collapsed);
}

export function loadLogScale(): boolean {
  return read(LOG_KEY) === '1';
}

/** Which intervals sit in the toolbar. Workspace-sticky like the interval itself: an
 *  operator picks the handful they actually switch between and keeps them everywhere. */
const DEFAULT_PINNED: ChartTimeframe[] = ['5m', '1h', 'D', 'W', 'M'];

export function loadPinnedTimeframes(): ChartTimeframe[] {
  const raw = read(PINNED_TIMEFRAMES_KEY);
  if (!raw) return DEFAULT_PINNED;
  try {
    const parsed = JSON.parse(raw);
    const valid = Array.isArray(parsed) ? parsed.filter((value): value is ChartTimeframe => isKnownTimeframe(value)) : [];
    // An empty or unreadable list means the defaults, not an empty toolbar.
    return valid.length ? valid : DEFAULT_PINNED;
  } catch {
    return DEFAULT_PINNED;
  }
}

export function savePinnedTimeframes(values: ChartTimeframe[]): void {
  write(PINNED_TIMEFRAMES_KEY, JSON.stringify(values));
}

function isKnownTimeframe(value: unknown): boolean {
  return typeof value === 'string'
    && (['D', 'W', 'M'] as string[]).includes(value) || (INTRADAY_TIMEFRAMES as readonly string[]).includes(value as string);
}

export function saveCandleStyle(style: CandleStyle): void {
  write(CANDLE_STYLE_KEY, style);
}

/** Workspace-sticky, like the interval and the log scale: an operator picks how they read a
 *  chart once and looks at every asset through it. */
export function loadCandleStyle(): CandleStyle {
  return read(CANDLE_STYLE_KEY) === 'heikin-ashi' ? 'heikin-ashi' : 'candles';
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
