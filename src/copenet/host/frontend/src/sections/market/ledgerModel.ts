// Pure derivations behind the Ledger section: how the model's calls performed over time.
// Scoring itself is the backend's (pre-registered rules); this only buckets what it returns.

import type { LedgerClaim, LedgerHorizonSlot, LedgerReport } from './types';

export type LedgerKind = LedgerClaim['kind'];

export interface WeekBucket {
  /** ISO date of the Monday that starts the week. */
  weekStart: string;
  correct: number;
  incorrect: number;
  push: number;
  pending: number;
}

function mondayOf(iso: string): string | null {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  const day = date.getUTCDay();
  const shift = (day + 6) % 7; // Monday = 0
  const monday = new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() - shift));
  return monday.toISOString().slice(0, 10);
}

/** Claims grouped by the week they were made, with the chosen horizon's outcome. Oldest
 *  first; weeks with no claims are omitted (a quiet week is not a wrong week). */
export function weeklyOutcomes(claims: readonly LedgerClaim[], horizon = '4w'): WeekBucket[] {
  const buckets = new Map<string, WeekBucket>();
  for (const claim of claims) {
    const weekStart = mondayOf(claim.created_at);
    if (!weekStart) continue;
    const bucket = buckets.get(weekStart) ?? { weekStart, correct: 0, incorrect: 0, push: 0, pending: 0 };
    const slot = claim.horizons?.[horizon];
    if (!slot?.resolved_at) bucket.pending += 1;
    else if (slot.outcome === 'correct') bucket.correct += 1;
    else if (slot.outcome === 'incorrect') bucket.incorrect += 1;
    else bucket.push += 1;
    buckets.set(weekStart, bucket);
  }
  return [...buckets.values()].sort((left, right) => left.weekStart.localeCompare(right.weekStart));
}

export function hitRate(bucket: Pick<WeekBucket, 'correct' | 'incorrect'>): number | null {
  const scored = bucket.correct + bucket.incorrect;
  return scored ? Math.round((bucket.correct / scored) * 100) : null;
}

export function claimIsScored(claim: LedgerClaim, horizon = '4w'): boolean {
  return Boolean(claim.horizons?.[horizon]?.resolved_at);
}


/** Days until a horizon scores, or null once it has. The page rendered "…" in every pending
 *  cell — 456 of them — which said "unknown" about something the ledger knows exactly. */
export function daysUntilDue(slot: LedgerHorizonSlot | undefined, now = Date.now()): number | null {
  if (!slot || slot.resolved_at) return null;
  const due = Date.parse(slot.due_at);
  if (!Number.isFinite(due)) return null;
  return Math.max(0, Math.ceil((due - now) / 86_400_000));
}

export interface LedgerScorecard {
  correct: number;
  scored: number;
  pct: number | null;
  /** Chance's hit rate over the same matched claims, where a baseline could be matched. */
  baselinePct: number | null;
  edge: number | null;
  pending: number;
}

/** The one question the page exists to answer: across every kind, is this better than chance?
 *  Four cards each held a piece of it and the operator had to do the arithmetic.
 *
 *  The baseline is a claim-weighted average of the per-kind baselines, using each kind's own
 *  matched-claim count — an unweighted mean would let a kind with three scored claims count
 *  as much as one with a hundred. */
export function overallScorecard(report: LedgerReport, horizon = '4w'): LedgerScorecard {
  let correct = 0;
  let scored = 0;
  let baselineWeighted = 0;
  let baselineWeight = 0;
  for (const kind of Object.keys(report.stats) as LedgerKind[]) {
    const stat = report.stats[kind]?.[horizon];
    if (stat) {
      correct += stat.correct;
      scored += stat.correct + stat.incorrect;
    }
    const baseline = report.baseline?.[kind]?.[horizon];
    if (baseline?.pct != null && baseline.matchedClaims > 0) {
      baselineWeighted += baseline.pct * baseline.matchedClaims;
      baselineWeight += baseline.matchedClaims;
    }
  }
  const pct = scored ? (correct / scored) * 100 : null;
  const baselinePct = baselineWeight ? baselineWeighted / baselineWeight : null;
  return {
    correct,
    scored,
    pct,
    baselinePct,
    edge: pct != null && baselinePct != null ? pct - baselinePct : null,
    pending: report.pendingHorizons,
  };
}

/** Claims grouped by the calendar day they were made, newest day first. The list repeated a
 *  date on every one of 349 rows instead of saying it once per day. */
export function groupByDay(claims: readonly LedgerClaim[]): { day: string; claims: LedgerClaim[] }[] {
  const days = new Map<string, LedgerClaim[]>();
  for (const claim of claims) {
    // The key must come off the same clock the heading formats with, or a late-UTC claim
    // groups under a day the rows beneath it disagree with.
    const at = new Date(claim.created_at);
    const day = Number.isNaN(at.getTime())
      ? claim.created_at.slice(0, 10)
      : `${at.getFullYear()}-${String(at.getMonth() + 1).padStart(2, '0')}-${String(at.getDate()).padStart(2, '0')}`;
    const bucket = days.get(day);
    if (bucket) bucket.push(claim);
    else days.set(day, [claim]);
  }
  return [...days.entries()].map(([day, dayClaims]) => ({ day, claims: dayClaims }));
}
