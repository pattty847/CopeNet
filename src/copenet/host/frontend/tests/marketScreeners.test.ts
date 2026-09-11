import assert from 'node:assert/strict';
import test from 'node:test';
import { sortCandidates } from '../src/sections/market/screeners/model';
import type { Candidate } from '../src/sections/market/screeners/types';
import { marketSectionFromLocation, marketSectionPath } from '../src/lib/appSectionRouting';

test('screeners have a first-class Market route', () => {
  assert.equal(marketSectionFromLocation('/market', '?view=screeners'), 'screeners');
  assert.equal(marketSectionPath('screeners'), '/market?view=screeners');
});

test('candidate sorting keeps unknown metrics last and leaves snapshot order unchanged', () => {
  const rows = [{ id: 'B', rsi: 35 }, { id: 'A', rsi: null }, { id: 'C', rsi: 60 }] as Candidate[];
  assert.deepEqual(sortCandidates(rows, 'rsi', false).map((row) => row.id), ['C', 'B', 'A']);
  assert.deepEqual(sortCandidates(rows, 'rsi', true).map((row) => row.id), ['B', 'C', 'A']);
  assert.deepEqual(rows.map((row) => row.id), ['B', 'A', 'C']);
});
