import assert from 'node:assert/strict';
import test from 'node:test';

import {
  observationTime,
  splitFinancialOverlaySegments,
} from '../src/sections/market/financialOverlay';
import type { FinancialSeriesObservation } from '../src/sections/market/types';

test('null financial observations split the plotted line into real gaps', () => {
  const segments = splitFinancialOverlaySegments([
    { t: 1, value: 10 },
    { t: 2, value: null },
    { t: 3, value: null },
    { t: 4, value: 20 },
    { t: 5, value: 21 },
  ]);

  assert.deepEqual(segments, [
    [{ t: 1, value: 10 }],
    [
      { t: 4, value: 20 },
      { t: 5, value: 21 },
    ],
  ]);
});

test('duplicate timestamps keep the latest point before segmentation', () => {
  const segments = splitFinancialOverlaySegments([
    { t: 1, value: 10 },
    { t: 1, value: null },
    { t: 2, value: 20 },
  ]);

  assert.deepEqual(segments, [[{ t: 2, value: 20 }]]);
});

test('financial overlays align observations to availableAt rather than periodEnd', () => {
  const observation = {
    periodEnd: '2025-03-31',
    availableAt: '2025-05-15',
  } as FinancialSeriesObservation;

  assert.equal(
    observationTime(observation),
    Math.floor(Date.parse('2025-05-15T00:00:00Z') / 1000),
  );
  assert.notEqual(
    observationTime(observation),
    Math.floor(Date.parse('2025-03-31T00:00:00Z') / 1000),
  );
});
