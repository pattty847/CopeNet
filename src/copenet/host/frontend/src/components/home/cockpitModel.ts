// What the Home cockpit shows, derived once and rendered dumbly.
//
// Home is a cold-open: one non-scrolling screen that answers "what is the market doing,
// what does my desk want from me, and where do I go next" before the operator has to
// choose anything. Every derivation here is pure so the screen can be reasoned about and
// tested without mounting it — the component only formats what these functions return.

import type { MissionControlItem } from '../../lib/missionControl';
import type {
  BriefMover,
  BriefSignalFlip,
  EvidenceItem,
  Portfolio,
  Tone,
  WatchlistItem,
} from '../../sections/market/types';

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

export interface TapeRow {
  symbol: string;
  name: string;
  value: string;
  change: string;
  changePct: number | null;
  tone: Tone;
  spark: number[];
  /** True when the operator actually holds it — a position outranks a watch. */
  held: boolean;
}

/** Watchlist rows carry a formatted change ("+6.10%"), not a number. Ranking needs the
 *  magnitude, so read it back rather than threading a second field through the RPC. */
function parsePct(change: string): number | null {
  const value = Number.parseFloat(change.replace(/[^0-9.+-]/g, ''));
  return Number.isFinite(value) ? value : null;
}

/** The tape: what the operator is actually watching, biggest movers first.
 *
 *  Held names are pinned above pure watches regardless of how much they moved — a 0.2%
 *  drift in something you own is more worth a glance than a 6% rip in something you do not.
 *  Movers from the morning brief fill in for symbols the watchlist has no quote for yet, so
 *  a cold cache still shows a tape instead of a row of dashes. */
export function buildTapeRows(
  watchlist: WatchlistItem[],
  movers: BriefMover[],
  portfolio: Portfolio | null,
  limit = 12,
): TapeRow[] {
  const held = new Set((portfolio?.positions ?? []).map((position) => position.symbol.toUpperCase()));
  const moverBySymbol = new Map(movers.map((mover) => [mover.symbol.toUpperCase(), mover]));
  const seen = new Set<string>();
  const rows: TapeRow[] = [];

  for (const item of watchlist) {
    const symbol = item.symbol.toUpperCase();
    if (seen.has(symbol)) continue;
    seen.add(symbol);
    const mover = moverBySymbol.get(symbol);
    rows.push({
      symbol,
      name: item.name,
      value: item.value,
      change: item.change,
      changePct: mover ? mover.changePct : parsePct(item.change),
      tone: item.tone,
      spark: item.spark ?? [],
      held: held.has(symbol),
    });
  }

  for (const mover of movers) {
    const symbol = mover.symbol.toUpperCase();
    if (seen.has(symbol)) continue;
    seen.add(symbol);
    rows.push({
      symbol,
      name: mover.name,
      value: mover.last,
      change: `${mover.changePct >= 0 ? '+' : ''}${mover.changePct.toFixed(2)}%`,
      changePct: mover.changePct,
      tone: mover.tone,
      spark: [],
      held: held.has(symbol),
    });
  }

  return rows
    .sort((a, b) => {
      if (a.held !== b.held) return a.held ? -1 : 1;
      return Math.abs(b.changePct ?? 0) - Math.abs(a.changePct ?? 0);
    })
    .slice(0, limit);
}

export interface AttentionRow {
  id: string;
  /** `blocking` renders red and sorts first — an approval or a failed run is a stop. */
  severity: 'blocking' | 'open' | 'idle';
  label: string;
  detail: string;
  meta: string;
  sessionKey: string;
  /** Where clicking the row lands. */
  destination: 'agents' | 'observability';
}

const SEVERITY_RANK: Record<AttentionRow['severity'], number> = { blocking: 0, open: 1, idle: 2 };

/** The desk's ask, flattened out of Mission Control's four lanes into one ranked list.
 *
 *  The lanes were a taxonomy for a full page; a cold-open has room for a queue. `recently
 *  useful` and `promote to workflow` are retrospective — interesting, never urgent — so they
 *  are dropped here rather than competing with a blocked approval for the same eight rows. */
export function buildAttentionRows(items: MissionControlItem[], limit = 8): AttentionRow[] {
  const rows: AttentionRow[] = [];
  for (const item of items) {
    if (item.lane !== 'needs_attention' && item.lane !== 'ready_to_continue') continue;
    const severity: AttentionRow['severity'] =
      item.kind === 'approval' || item.kind === 'failed_run'
        ? 'blocking'
        : item.lane === 'needs_attention'
          ? 'open'
          : 'idle';
    rows.push({
      id: item.id,
      severity,
      label: item.title,
      detail: item.detail,
      meta: item.meta,
      sessionKey: item.sessionKey,
      destination: item.kind === 'failed_run' ? 'observability' : 'agents',
    });
  }
  return rows.sort((a, b) => SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]).slice(0, limit);
}

export interface ChangeRow {
  id: string;
  symbol: string;
  /** Short caps tag: the kind of change, not the source system. */
  kind: string;
  detail: string;
  tone: Tone;
  /** Which Market section explains it. */
  view: 'evidence' | 'signals';
}

/** What moved since the last sweep, as one list.
 *
 *  The brief splits its changes by provenance — new filings, signal flips, rotation shifts —
 *  which is the right shape for the Market page, where each has a section that explains it.
 *  Home has room for a glance, so they are interleaved and capped: evidence first because a
 *  filing is a fact and a signal flip is a reading of one. */
export function buildChangeRows(
  newEvidence: EvidenceItem[],
  signalFlips: BriefSignalFlip[],
  limit = 10,
): ChangeRow[] {
  const rows: ChangeRow[] = newEvidence.map((item, index) => ({
    id: `evidence:${item.symbol}:${index}`,
    symbol: item.symbol,
    kind: item.type,
    detail: item.headline,
    tone: item.tone,
    view: 'evidence' as const,
  }));
  for (const [index, flip] of signalFlips.entries()) {
    rows.push({
      id: `flip:${flip.symbol}:${index}`,
      symbol: flip.symbol,
      kind: flip.kind,
      detail: flip.detail,
      tone: flip.tone,
      view: 'signals',
    });
  }
  return rows.slice(0, limit);
}
