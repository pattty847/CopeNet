import assert from 'node:assert/strict';
import test from 'node:test';

import { buildSecActivityRows, formatSecActivityValue } from '../src/sections/market/secActivity';
import type { EvidenceItem } from '../src/sections/market/types';

const evidence: EvidenceItem[] = [
  { type: 'Insider', symbol: 'TEST', headline: 'Cluster buy', source: 'Form 4', tone: 'up', flag: 'cluster', t: Date.parse('2026-01-10T00:00:00Z') / 1000, value: 2_500_000 },
  { type: 'Insider', symbol: 'TEST', headline: 'Acquisition', source: 'Form 4', tone: 'up', t: Date.parse('2026-01-10T00:00:00Z') / 1000, value: 2_000_000, shares: 20_000 },
  { type: 'Insider', symbol: 'TEST', headline: 'Disposition', source: 'Form 4', tone: 'down', t: Date.parse('2026-01-10T12:00:00Z') / 1000, value: 500_000, shares: 5_000 },
  { type: 'Form 144', symbol: 'TEST', headline: 'Intended sale', source: 'Form 144', tone: 'down', t: Date.parse('2026-01-10T18:00:00Z') / 1000, value: 4_000_000, shares: 40_000 },
  { type: '8-K', symbol: 'TEST', headline: 'Results', source: '8-K', tone: 'flat', t: Date.parse('2026-02-02T00:00:00Z') / 1000 },
];

test('SEC activity separates executed trades from planned sales and ignores aggregate clusters', () => {
  const rows = buildSecActivityRows(evidence, 'money');

  assert.equal(rows.length, 1);
  assert.equal(rows[0].executedValue, 1_500_000);
  assert.equal(rows[0].plannedValue, -4_000_000);
  assert.equal(rows[0].buys, 1);
  assert.equal(rows[0].sells, 1);
  assert.equal(rows[0].plannedSales, 1);
  assert.equal(rows[0].executedPercentile, 100);
  assert.equal(rows[0].plannedPercentile, 100);
});

test('SEC activity can express signed share counts', () => {
  const rows = buildSecActivityRows(evidence, 'shares');
  assert.equal(rows[0].executedValue, 15_000);
  assert.equal(rows[0].plannedValue, -40_000);
  assert.equal(formatSecActivityValue(rows[0].executedValue, 'shares'), '+15K sh');
  assert.equal(formatSecActivityValue(rows[0].plannedValue, 'money'), '−$40K');
});

test('SEC activity retains every active date in the selected evidence window', () => {
  const longWindow = Array.from({ length: 30 }, (_, index): EvidenceItem => ({
    type: 'Insider', symbol: 'TEST', headline: 'Acquisition', source: 'Form 4', tone: 'up',
    t: Date.parse(`2026-01-${String(index + 1).padStart(2, '0')}T00:00:00Z`) / 1000,
    value: index + 1,
  }));
  assert.equal(buildSecActivityRows(longWindow, 'money').length, 30);
});
