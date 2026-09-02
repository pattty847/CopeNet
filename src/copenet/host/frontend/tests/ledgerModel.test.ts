import assert from 'node:assert/strict';
import test from 'node:test';
import { claimIsScored, hitRate, weeklyOutcomes } from '../src/sections/market/ledgerModel';
import type { LedgerClaim } from '../src/sections/market/types';

const claim = (created: string, outcome: LedgerClaim['horizons'][string]['outcome'] | 'pending'): LedgerClaim => ({
  claim_id: `${created}-${outcome}`,
  created_at: created,
  kind: 'attention',
  target: 'NVDA',
  value: 'attention',
  model: 'gpt-5.5',
  note: 'why',
  horizons: outcome === 'pending' ? { '4w': { due_at: '2026-10-01' } } : { '4w': { due_at: '2026-10-01', resolved_at: '2026-10-01', outcome } },
});

test('ledger outcomes bucket by ISO week, oldest first, and skip empty weeks', () => {
  const weeks = weeklyOutcomes([
    claim('2026-08-19T10:00:00Z', 'correct'), // Wed → week of Aug 17
    claim('2026-08-23T10:00:00Z', 'incorrect'), // Sun → same week
    claim('2026-09-01T10:00:00Z', 'pending'), // Tue → week of Aug 31
    claim('2026-08-05T10:00:00Z', 'push'),
  ]);
  assert.deepEqual(weeks.map((week) => week.weekStart), ['2026-08-03', '2026-08-17', '2026-08-31']);
  assert.deepEqual(weeks[1], { weekStart: '2026-08-17', correct: 1, incorrect: 1, push: 0, pending: 0 });
  assert.equal(hitRate(weeks[1]), 50);
  assert.equal(hitRate(weeks[2]), null, 'a week with nothing scored has no rate');
  assert.equal(claimIsScored(claim('2026-09-01T10:00:00Z', 'pending')), false);
  assert.equal(claimIsScored(claim('2026-09-01T10:00:00Z', 'correct')), true);
});
