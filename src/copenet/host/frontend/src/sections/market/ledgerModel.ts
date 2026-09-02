// Pure derivations behind the Ledger section: how the model's calls performed over time.
// Scoring itself is the backend's (pre-registered rules); this only buckets what it returns.

import type { LedgerClaim } from './types';

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
