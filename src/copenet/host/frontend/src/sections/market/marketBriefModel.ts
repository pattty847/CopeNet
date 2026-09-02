// Pure derivations behind the Briefing section.
//
// The sweep already knows what changed; this file only decides how those changes are ranked
// and grouped for the first screen, and it does so once so the table, the count and the
// keyboard all agree. No fetching, no React.

import type { BriefMover, DashboardPayload, MorningBriefPayload, PortfolioPosition, RrgSector, Tone, WatchlistItem } from './types';

export interface MatterItem {
  key: string;
  /** Short category tag: the evidence type ('Insider', '8-K', …), 'soft-bottoming', 'trend', 'rotation'. */
  kind: string;
  symbol: string;
  text: string;
  tone: Tone;
  /** Where this came from, as the operator would name it: 'SEC Form 4 · Aug 31', 'signal flip', 'relative rotation'. */
  source: string;
  url?: string | null;
}

/** How many matters the briefing shows before asking. Six fits above the fold at 1280×720
 *  beside the standing picture; the count and "all →" say what was cut. */
export const MATTERS_VISIBLE = 6;

function evidenceDate(t?: number | null): string {
  if (!t || !Number.isFinite(t)) return '';
  const parsed = new Date(t * 1000);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString([], { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

/** Rank what changed by how much it should interrupt a glance: flagged SEC evidence
 *  (clusters, high-signal 8-Ks) > signal flips > rotation moves > the rest of the filings.
 *  This is the ordering the morning brief has always used; the table is just a wider view
 *  of the same list. */
export function composeMatters(brief: MorningBriefPayload): MatterItem[] {
  const items: MatterItem[] = [];
  const flagged = brief.newEvidence.filter((entry) => entry.flag);
  const plain = brief.newEvidence.filter((entry) => !entry.flag);
  const evidenceSource = (source: string, t?: number | null) => {
    const when = evidenceDate(t);
    return when ? `${source} · ${when}` : source;
  };
  flagged.forEach((entry, index) =>
    items.push({ key: `evf-${index}`, kind: entry.type, symbol: entry.symbol, text: entry.headline, tone: entry.tone, source: evidenceSource(entry.source, entry.t), url: entry.url }),
  );
  brief.signalFlips.forEach((flip, index) =>
    items.push({ key: `flip-${index}`, kind: flip.kind, symbol: flip.symbol, text: flip.detail, tone: flip.tone, source: 'signal flip' }),
  );
  brief.rrgShifts.forEach((shift, index) =>
    items.push({ key: `rrg-${index}`, kind: 'rotation', symbol: shift.symbol, text: `${shift.fromQuadrant} → ${shift.toQuadrant}`, tone: shift.tone, source: 'relative rotation' }),
  );
  plain.forEach((entry, index) =>
    items.push({ key: `ev-${index}`, kind: entry.type, symbol: entry.symbol, text: entry.headline, tone: entry.tone, source: evidenceSource(entry.source, entry.t), url: entry.url }),
  );
  return items;
}

/** "6 of 15 · all →" — a cap is only honest when it says what it cut. */
export function truncationLabel(shown: number, total: number): string {
  return `${shown} of ${total} · all →`;
}

export const RRG_QUADRANTS = ['leading', 'improving', 'weakening', 'lagging'] as const;
export type RrgQuadrant = (typeof RRG_QUADRANTS)[number];

/** Sector chips grouped by quadrant: the glanceable proxy for the rotation chart. */
export function rotationQuadrants(sectors: readonly RrgSector[]): Record<RrgQuadrant, RrgSector[]> {
  const groups: Record<RrgQuadrant, RrgSector[]> = { leading: [], improving: [], weakening: [], lagging: [] };
  for (const sector of sectors) groups[sector.quadrant].push(sector);
  return groups;
}

export function formatBreadth(value: number): string {
  return Number.isFinite(value) ? `${Math.round(value)}%` : '—';
}

export function formatVix(value: number): string {
  return Number.isFinite(value) ? value.toFixed(1) : '—';
}

export function regimeLabel(value: string): string {
  const labels: Record<string, string> = { 'risk-off': 'Risk-off', chop: 'Chop', 'risk-on': 'Risk-on', 'event-risk': 'Event-risk' };
  return labels[value] ?? value;
}

export const REGIME_ORDER = ['risk-off', 'chop', 'risk-on', 'event-risk'] as const;

// ----------------------------------------------------------------------- rail

export interface RailEntry {
  group: string;
  symbol: string;
  name: string;
  change?: string;
  tone?: Tone;
  spark?: number[];
  /** Only watched rows carry a remove control. */
  watched: boolean;
}

/** The active list in its own order, then holdings not on it, then unwatched movers. The
 *  flat symbol order is what j/k steps through, so it must match what the rail renders. */
export function buildWorkstationRail(
  watchlist: { items: WatchlistItem[]; active: string; symbols: Set<string> },
  holdings: readonly PortfolioPosition[],
  movers: readonly BriefMover[],
): RailEntry[] {
  const entries: RailEntry[] = watchlist.items.map((item) => ({
    group: watchlist.active,
    symbol: item.symbol,
    name: item.name,
    change: item.change,
    tone: item.tone,
    spark: item.spark,
    watched: true,
  }));
  const seen = new Set(watchlist.symbols);
  for (const position of holdings) {
    if (seen.has(position.symbol)) continue;
    seen.add(position.symbol);
    entries.push({ group: 'Holdings', symbol: position.symbol, name: position.symbol, change: position.pnlPct, tone: position.tone, watched: false });
  }
  for (const mover of movers) {
    if (seen.has(mover.symbol)) continue;
    seen.add(mover.symbol);
    entries.push({
      group: 'Movers',
      symbol: mover.symbol,
      name: mover.name,
      change: `${mover.changePct > 0 ? '+' : ''}${mover.changePct.toFixed(1)}%`,
      tone: mover.tone,
      watched: false,
    });
  }
  return entries;
}

export function stepSymbols(symbols: readonly string[], current: string | null, delta: -1 | 1): string | null {
  if (!symbols.length) return null;
  const at = current ? symbols.indexOf(current) : -1;
  if (at === -1) return delta === 1 ? symbols[0] : symbols[symbols.length - 1];
  return symbols[Math.min(symbols.length - 1, Math.max(0, at + delta))];
}

/** Rare, calibrated flags earn a permanent line on the briefing; everything enumerable lives
 *  in Signals. Capped so a busy screen never turns the standing picture into a list. */
export const FLAGGED_SETUPS_VISIBLE = 6;

export function flaggedSetups(dashboard: DashboardPayload) {
  return (dashboard.softBottoming?.data ?? []).slice(0, FLAGGED_SETUPS_VISIBLE);
}
