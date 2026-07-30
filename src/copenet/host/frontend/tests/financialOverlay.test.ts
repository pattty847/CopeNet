import assert from 'node:assert/strict';
import test from 'node:test';

import { splitFinancialOverlaySegments } from '../src/sections/market/financialOverlay';

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
