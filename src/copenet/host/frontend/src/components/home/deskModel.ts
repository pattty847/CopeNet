// What the Home desk shows, derived once and rendered dumbly.
//
// Home answers four questions the operator has on landing: what is the market doing, what
// is on my tape, what did my agents just do, and what did I tell myself to do today. Every
// derivation is pure so the page can be reasoned about and tested without mounting it — the
// panels only format what these functions return.

import type { MacroItem, Tone, WatchlistItem } from '../../sections/market/types';

/** Where the US equity session is right now, in the operator's terms rather than UTC. */
export type SessionPhase = 'pre' | 'open' | 'after' | 'closed';

export interface MarketClock {
  phase: SessionPhase;
  /** Caps label for the bar, e.g. "MKT OPEN". */
  label: string;
  /** Exchange-local time, e.g. "09:41 EDT". */
  time: string;
}

const PHASE_LABELS: Record<SessionPhase, string> = {
  pre: 'PRE-MARKET',
  open: 'MKT OPEN',
  after: 'AFTER HOURS',
  closed: 'MKT CLOSED',
};

/** Exchange-local wall clock. Weekend and holiday-free: a holiday reads as "closed" only
 *  once the clock passes 16:00, which is honest enough for a status chip and needs no
 *  calendar. The Market page owns the authoritative freshness stamp. */
export function marketClock(now: Date = new Date()): MarketClock {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    weekday: 'short',
    timeZoneName: 'short',
  }).formatToParts(now);
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  const hour = Number(get('hour'));
  const minute = Number(get('minute'));
  const weekday = get('weekday');
  const time = `${get('hour')}:${get('minute')} ${get('timeZoneName')}`;
  const minutes = hour * 60 + minute;

  const weekend = weekday === 'Sat' || weekday === 'Sun';
  const phase: SessionPhase = weekend
    ? 'closed'
    : minutes < 4 * 60
      ? 'closed'
      : minutes < 9 * 60 + 30
        ? 'pre'
        : minutes < 16 * 60
          ? 'open'
          : minutes < 20 * 60
            ? 'after'
            : 'closed';

  return { phase, label: PHASE_LABELS[phase], time };
}

// ------------------------------------------------------------------------- market pulse

export interface PulseTab {
  id: string;
  label: string;
  /** `watchlist` tabs are the operator's own lists — including whatever this morning's
   *  screener dropped into one. `macro` is the fixed cross-asset strip. */
  kind: 'watchlist' | 'macro';
}

export const MACRO_PULSE_TAB: PulseTab = { id: 'macro', label: 'Macro', kind: 'macro' };

/** The pulse tabs are the operator's watchlists, not a fixed set of asset classes.
 *
 *  A screener that surfaces ten to fifteen names each morning writes them to a watchlist;
 *  making the tabs follow the lists means those names appear here with no code change. The
 *  macro strip is appended rather than being one of the lists, because it comes from the
 *  dashboard rather than from anything the operator curates. */
export function buildPulseTabs(lists: readonly string[]): PulseTab[] {
  const tabs = lists
    .filter((name) => name.trim())
    .map((name) => ({ id: `watchlist:${name}`, label: name, kind: 'watchlist' as const }));
  return [...tabs, MACRO_PULSE_TAB];
}

export interface PulseRow {
  symbol: string;
  name: string;
  value: string;
  change: string;
  tone: Tone;
  spark: number[];
  /** Macro rows are indices and yields, not tradeable tickers — they open no chart. */
  navigable: boolean;
}

export function pulseRows(tab: PulseTab, watchlist: readonly WatchlistItem[], macro: readonly MacroItem[]): PulseRow[] {
  if (tab.kind === 'macro') {
    return macro.map((item) => ({
      symbol: item.label,
      name: item.label,
      value: item.value,
      change: item.change,
      tone: item.tone,
      spark: item.spark ?? [],
      navigable: false,
    }));
  }
  return watchlist.map((item) => ({
    symbol: item.symbol,
    name: item.name,
    value: item.value,
    change: item.change,
    tone: item.tone,
    spark: item.spark ?? [],
    navigable: true,
  }));
}

// -------------------------------------------------------------------------- desk health

/** "742 ms" / "2.4 s", or an em dash when nothing completed in the window.
 *  Never "0 ms": that reads as an impossibly fast desk rather than an idle one. */
export function formatLatency(ms: number | null): string {
  if (ms == null) return '—';
  return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)} s`;
}

/** A rate over no runs is unknown, not zero — say so rather than claiming a clean hour
 *  the desk never had. */
export function formatErrorRate(rate: number, runs: number): string {
  if (runs === 0) return '—';
  return `${(rate * 100).toFixed(rate >= 0.1 ? 0 : 1)}%`;
}

export function formatCount(value: number): string {
  return value >= 10_000 ? `${(value / 1000).toFixed(1)}k` : value.toLocaleString();
}

/** Relative age for an activity row: the desk cares about "9 minutes ago", never the date. */
export function relativeAge(iso: string, now: number = Date.now()): string {
  const then = Date.parse(iso);
  if (!Number.isFinite(then)) return '';
  const minutes = Math.max(0, Math.round((now - then) / 60_000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
