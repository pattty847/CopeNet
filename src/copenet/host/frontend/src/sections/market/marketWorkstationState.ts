// Persisted preferences and pure layout rules for the market workstation.
//
// How the operator likes to look at THE MARKET — which section they were in, whether the
// rail is open, how dense the page is, how each section's panels are arranged, and when
// they last opened each section — is sticky across visits. Nothing here is data; losing it
// costs a keypress. Every rule that decides a layout is a pure function so it can be tested
// without a DOM.

import type { MarketSection } from '../../lib/appSectionRouting';
import type { MorningBriefPayload } from './types';

export const MARKET_SECTION_TABS: { id: MarketSection; label: string; hint: string }[] = [
  { id: 'briefing', label: 'Briefing', hint: 'What changed, the standing picture, the model read' },
  { id: 'structure', label: 'Structure', hint: 'Rates and relative rotation' },
  { id: 'signals', label: 'Signals', hint: 'Soft bottoming, accumulation, trend' },
  { id: 'portfolio', label: 'Portfolio', hint: 'Positions, speculative lane, P&L, fills' },
  { id: 'evidence', label: 'Evidence', hint: 'Filings and news' },
  { id: 'ledger', label: 'Ledger', hint: 'Forward ledger and calibration' },
  { id: 'backtest', label: 'Backtest', hint: 'Portfolio backtests and stress scenarios' },
  { id: 'scans', label: 'Scans & alerts', hint: 'Asset scope, schedules, technical alerts and delivery' },
];

/** The rail is the watchlist as a destination on screens too narrow to keep it open. */
export const WATCHLIST_TAB: { id: MarketSection; label: string; hint: string } = { id: 'watchlist', label: 'Watchlist', hint: 'Tracked symbols' };

/** Below this the rail starts collapsed; the operator can still open it. */
export const RAIL_AUTO_COLLAPSE_PX = 1366;
/** Below this the rail is not rendered at all and the watchlist becomes a tab. */
export const RAIL_HIDDEN_PX = 900;

export type Density = 'compact' | 'comfortable';
export type PanelWidth = 'half' | 'full';

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value == null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* private mode — preferences are a convenience, never a requirement */
  }
}

const SECTION_KEY = 'mm-mw-section';
const RAIL_KEY = 'mm-mw-rail';
const DENSITY_KEY = 'mm-mw-density';
const VISITS_KEY = 'mm-mw-visits';
const LAYOUT_KEY_PREFIX = 'mm-mw-layout-';

// ------------------------------------------------------------------ section

export function loadLastSection(): MarketSection {
  const stored = read(SECTION_KEY);
  return MARKET_SECTION_TABS.some((tab) => tab.id === stored) ? (stored as MarketSection) : 'briefing';
}

export function saveLastSection(section: MarketSection): void {
  // The watchlist tab is a narrow-screen stand-in for the rail; remembering it would land a
  // desktop visit on a section that does not exist there.
  if (section === 'watchlist') return;
  write(SECTION_KEY, section);
}

// --------------------------------------------------------------------- rail

/** null = no explicit choice yet; the width rule decides. */
export function loadRailPreference(): boolean | null {
  const stored = read(RAIL_KEY);
  return stored === '1' ? true : stored === '0' ? false : null;
}

export function saveRailPreference(collapsed: boolean): void {
  write(RAIL_KEY, collapsed ? '1' : '0');
}

export function railCollapsed(preference: boolean | null, viewportWidth: number): boolean {
  return preference ?? viewportWidth < RAIL_AUTO_COLLAPSE_PX;
}

// ------------------------------------------------------------------ density

export function loadDensity(): Density {
  return read(DENSITY_KEY) === 'comfortable' ? 'comfortable' : 'compact';
}

export function saveDensity(density: Density): void {
  write(DENSITY_KEY, density);
}

// ------------------------------------------------------------- section visits

export type SectionVisits = Partial<Record<MarketSection, string>>;

export function loadSectionVisits(): SectionVisits {
  const raw = read(VISITS_KEY);
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const visits: SectionVisits = {};
    for (const tab of MARKET_SECTION_TABS) {
      const value = parsed[tab.id];
      if (typeof value === 'string') visits[tab.id] = value;
    }
    return visits;
  } catch {
    return {};
  }
}

export function saveSectionVisits(visits: SectionVisits): void {
  write(VISITS_KEY, JSON.stringify(visits));
}

/** A section tab carries a count when the last sweep delivered something into it after the
 *  operator last opened it — the tab strip doubles as an inbox. Only the sweep's own delta
 *  lists count; standing lists are not "new". */
export function sectionNewCounts(brief: MorningBriefPayload | null, visits: SectionVisits): Partial<Record<MarketSection, number>> {
  if (!brief) return {};
  const swept = Date.parse(brief.generatedAt);
  if (!Number.isFinite(swept)) return {};
  const unseen = (section: MarketSection) => {
    const visited = visits[section];
    if (!visited) return true;
    const at = Date.parse(visited);
    return !Number.isFinite(at) || at < swept;
  };
  const counts: Partial<Record<MarketSection, number>> = {};
  if (unseen('evidence') && brief.newEvidence.length) counts.evidence = brief.newEvidence.length;
  if (unseen('signals') && brief.signalFlips.length) counts.signals = brief.signalFlips.length;
  if (unseen('structure') && brief.rrgShifts.length) counts.structure = brief.rrgShifts.length;
  return counts;
}

// ------------------------------------------------------------ section layout

export interface SectionPanelSpec {
  id: string;
  title: string;
  defaultWidth: PanelWidth;
  /** Panels that only read at full width (tables, the yield curve) cannot be halved. */
  canHalf: boolean;
}

export interface SectionLayoutPref {
  order: string[];
  hidden: string[];
  width: Record<string, PanelWidth>;
}

export interface ResolvedPanel<T extends SectionPanelSpec = SectionPanelSpec> {
  spec: T;
  width: PanelWidth;
  hidden: boolean;
}

const EMPTY_LAYOUT: SectionLayoutPref = { order: [], hidden: [], width: {} };

export function loadSectionLayout(section: MarketSection): SectionLayoutPref {
  const raw = read(`${LAYOUT_KEY_PREFIX}${section}`);
  if (!raw) return EMPTY_LAYOUT;
  try {
    const parsed = JSON.parse(raw) as Partial<SectionLayoutPref>;
    return {
      order: Array.isArray(parsed.order) ? parsed.order.filter((id): id is string => typeof id === 'string') : [],
      hidden: Array.isArray(parsed.hidden) ? parsed.hidden.filter((id): id is string => typeof id === 'string') : [],
      width: parsed.width && typeof parsed.width === 'object' ? Object.fromEntries(Object.entries(parsed.width).filter(([, value]) => value === 'half' || value === 'full')) as Record<string, PanelWidth> : {},
    };
  } catch {
    return EMPTY_LAYOUT;
  }
}

export function saveSectionLayout(section: MarketSection, pref: SectionLayoutPref | null): void {
  write(`${LAYOUT_KEY_PREFIX}${section}`, pref ? JSON.stringify(pref) : null);
}

/** Stored order wins for panels that still exist, new panels append at their default slot,
 *  unknown ids drop — so adding or removing a panel never strands a saved layout. Hidden
 *  panels stay in the list (the arrange menu needs them) with `hidden: true`. */
export function resolveSectionLayout<T extends SectionPanelSpec>(panels: readonly T[], pref: SectionLayoutPref, isMobile = false): ResolvedPanel<T>[] {
  if (isMobile) return panels.map((spec) => ({ spec, width: 'full', hidden: false }));
  const byId = new Map(panels.map((panel) => [panel.id, panel]));
  const ordered: T[] = [];
  for (const id of pref.order) {
    const panel = byId.get(id);
    if (panel && !ordered.includes(panel)) ordered.push(panel);
  }
  for (const panel of panels) if (!ordered.includes(panel)) ordered.push(panel);
  return ordered.map((spec) => {
    const stored = pref.width[spec.id];
    const width: PanelWidth = stored === 'half' && !spec.canHalf ? 'full' : stored ?? spec.defaultWidth;
    return { spec, width, hidden: pref.hidden.includes(spec.id) };
  });
}

export function movePanel(pref: SectionLayoutPref, panelIds: string[], id: string, delta: -1 | 1): SectionLayoutPref {
  const order = pref.order.length ? [...pref.order] : [...panelIds];
  for (const panelId of panelIds) if (!order.includes(panelId)) order.push(panelId);
  const index = order.indexOf(id);
  const target = index + delta;
  if (index === -1 || target < 0 || target >= order.length) return pref;
  [order[index], order[target]] = [order[target], order[index]];
  return { ...pref, order };
}

export function togglePanelHidden(pref: SectionLayoutPref, id: string): SectionLayoutPref {
  const hidden = pref.hidden.includes(id) ? pref.hidden.filter((entry) => entry !== id) : [...pref.hidden, id];
  return { ...pref, hidden };
}

export function setPanelWidth(pref: SectionLayoutPref, id: string, width: PanelWidth): SectionLayoutPref {
  return { ...pref, width: { ...pref.width, [id]: width } };
}
