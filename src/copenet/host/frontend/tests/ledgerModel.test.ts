import assert from 'node:assert/strict';
import test from 'node:test';

import { daysUntilDue, groupByDay, overallScorecard } from '../src/sections/market/ledgerModel';
import type { LedgerClaim, LedgerKindStats, LedgerReport } from '../src/sections/market/types';

function claim(id: string, createdAt: string, kind: LedgerClaim['kind'] = 'attention'): LedgerClaim {
  return { claim_id: id, created_at: createdAt, kind, target: 'AAA', value: kind, model: 'test', note: '', horizons: {} };
}

function stats(correct: number, incorrect: number): LedgerKindStats {
  const scored = correct + incorrect;
  return { correct, incorrect, push: 0, accuracyPct: scored ? (correct / scored) * 100 : null };
}

test('the overall scorecard weights each kind baseline by its own matched claims', () => {
  const report = {
    rulesVersion: 'v1',
    totalClaims: 0,
    pendingHorizons: 12,
    signals: {},
    recent: [],
    stats: {
      regime: { '4w': stats(60, 40) },
      attention: { '4w': stats(5, 5) },
      lean: { '4w': stats(0, 0) },
      screen: { '4w': stats(0, 0) },
    },
    baseline: {
      // A kind with 100 matched claims must not be outvoted by one with 10.
      regime: { '4w': { pct: 80, n: 100, label: 'dart', matchedClaims: 100, scoredClaims: 100, accuracyPct: 60 } },
      attention: { '4w': { pct: 30, n: 10, label: 'dart', matchedClaims: 10, scoredClaims: 10, accuracyPct: 50 } },
      lean: { '4w': { pct: null, n: 0, label: 'dart', matchedClaims: 0, scoredClaims: 0, accuracyPct: null } },
      screen: { '4w': { pct: null, n: 0, label: 'dart', matchedClaims: 0, scoredClaims: 0, accuracyPct: null } },
    },
  } as unknown as LedgerReport;

  const card = overallScorecard(report);
  assert.equal(card.correct, 65);
  assert.equal(card.scored, 110);
  assert.equal(Math.round(card.pct!), 59);
  // (80*100 + 30*10) / 110 — not the unweighted mean of 55.
  assert.equal(Math.round(card.baselinePct!), 75);
  assert.equal(Math.round(card.edge!), -16);
  assert.equal(card.pending, 12);
});

test('a scorecard with nothing resolved reports no rate rather than zero', () => {
  const report = {
    pendingHorizons: 4,
    stats: { regime: { '4w': stats(0, 0) }, attention: {}, lean: {}, screen: {} },
    baseline: {},
  } as unknown as LedgerReport;
  const card = overallScorecard(report);
  assert.equal(card.scored, 0);
  assert.equal(card.pct, null);
  assert.equal(card.edge, null);
});

test('claims group under the local calendar day their timestamp falls on', () => {
  // A late-UTC stamp must not be filed under a day the row's own rendered date disagrees with.
  const late = new Date(2026, 8, 7, 20, 30).toISOString();
  const earlier = new Date(2026, 8, 7, 9, 15).toISOString();
  const dayBefore = new Date(2026, 8, 6, 9, 15).toISOString();

  const groups = groupByDay([claim('a', late), claim('b', earlier), claim('c', dayBefore)]);
  assert.equal(groups.length, 2);
  assert.equal(groups[0].day, '2026-09-07');
  assert.equal(groups[0].claims.length, 2);
  assert.equal(groups[1].day, '2026-09-06');
});

test('a pending horizon reports days remaining, and a resolved one reports none', () => {
  const now = Date.parse('2026-09-07T00:00:00Z');
  assert.equal(daysUntilDue({ due_at: '2026-10-05T00:00:00Z' }, now), 28);
  assert.equal(daysUntilDue({ due_at: '2026-09-01T00:00:00Z' }, now), 0, 'an overdue horizon is 0d, never negative');
  assert.equal(daysUntilDue({ due_at: '2026-10-05T00:00:00Z', resolved_at: '2026-10-05T00:00:00Z' }, now), null);
  assert.equal(daysUntilDue(undefined, now), null);
});
