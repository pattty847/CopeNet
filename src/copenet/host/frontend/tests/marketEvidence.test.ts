import assert from 'node:assert/strict';
import test from 'node:test';

import { sortEvidenceNewestFirst } from '../src/sections/market/marketEvidence';
import type { EvidenceItem } from '../src/sections/market/types';

function evidence(headline: string, t?: number): EvidenceItem {
  return {
    type: 'Insider',
    symbol: 'TEST',
    headline,
    source: 'Form 4',
    tone: 'flat',
    t,
  };
}

test('SEC evidence sorts newest first without mutating the payload', () => {
  const oldest = evidence('Oldest', 100);
  const newest = evidence('Newest', 300);
  const middle = evidence('Middle', 200);
  const payload = [oldest, newest, middle];

  const sorted = sortEvidenceNewestFirst(payload);

  assert.deepEqual(sorted.map((item) => item.headline), ['Newest', 'Middle', 'Oldest']);
  assert.deepEqual(payload, [oldest, newest, middle]);
});

test('undated SEC evidence stays at the bottom', () => {
  const sorted = sortEvidenceNewestFirst([
    evidence('Undated'),
    evidence('Dated', 100),
  ]);

  assert.deepEqual(sorted.map((item) => item.headline), ['Dated', 'Undated']);
});
