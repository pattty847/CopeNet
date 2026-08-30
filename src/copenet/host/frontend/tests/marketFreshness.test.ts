import assert from 'node:assert/strict';
import test from 'node:test';
import { dataFreshness } from '../src/sections/market/marketUi';

const NOW = Date.parse('2026-08-30T12:00:00Z');

test('market timestamps use the shared three-tier freshness rule', () => {
  assert.equal(dataFreshness('2026-08-30T12:00:00Z', NOW), 'fresh');
  assert.equal(dataFreshness('2026-08-27T12:00:00Z', NOW), 'fresh');
  assert.equal(dataFreshness('2026-08-26T12:00:00Z', NOW), 'aging');
  assert.equal(dataFreshness('2026-08-25T12:00:00Z', NOW), 'aging');
  assert.equal(dataFreshness('2026-08-24T12:00:00Z', NOW), 'stale');
});

test('unknown timestamps stay neutral', () => {
  assert.equal(dataFreshness(undefined, NOW), 'unknown');
  assert.equal(dataFreshness('not-a-date', NOW), 'unknown');
});
