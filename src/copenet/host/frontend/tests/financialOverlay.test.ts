import assert from 'node:assert/strict';
import test from 'node:test';

import {
  hasRenderableFinancialOverlay,
  observationTime,
  snapOverlayToCandles,
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

test('an all-null valuation is not treated as a renderable chart axis', () => {
  assert.equal(hasRenderableFinancialOverlay([
    { t: 1, value: null },
    { t: 2, value: Number.NaN },
  ]), false);
  assert.equal(hasRenderableFinancialOverlay([{ t: 1, value: -0.05 }]), true);
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

// Lightweight Charts' time axis is index-based: every unique timestamp across every
// attached series takes one equal-width slot. An overlay point on its own filing date
// therefore INSERTS a slot rather than sitting between two candles.

test('overlay points snap forward onto the next candle, never backward', () => {
  const candles = [100, 200, 300];

  // 150 is a filing that landed between two bars — it becomes visible on the next one.
  assert.deepEqual(
    snapOverlayToCandles([{ t: 150, value: 5 }], candles),
    [{ t: 200, value: 5 }],
  );
  // Snapping backward would draw a filing before it was public — the same lookahead that
  // aligning to availableAt exists to prevent.
  assert.deepEqual(
    snapOverlayToCandles([{ t: 199, value: 5 }], candles),
    [{ t: 200, value: 5 }],
  );
});

test('a point landing exactly on a candle stays put', () => {
  assert.deepEqual(
    snapOverlayToCandles([{ t: 200, value: 5 }], [100, 200, 300]),
    [{ t: 200, value: 5 }],
  );
});

test('snapping adds no timestamps the candles do not already have', () => {
  const candles = [100, 200, 300, 400];
  const snapped = snapOverlayToCandles(
    [
      { t: 110, value: 1 },
      { t: 250, value: 2 },
      { t: 399, value: 3 },
    ],
    candles,
  );

  // The whole point: zero injected slots, so barSpacing keeps meaning "one candle".
  assert.equal(snapped.every((point) => candles.includes(point.t)), true);
});

test('points outside the candle range are dropped rather than clamped', () => {
  const candles = [100, 200, 300];

  // Before the first candle: clamping forward would pile every pre-chart filing onto bar one.
  assert.deepEqual(snapOverlayToCandles([{ t: 50, value: 5 }], candles), []);
  // After the last: pinned to the right edge it would read as current data.
  assert.deepEqual(snapOverlayToCandles([{ t: 999, value: 5 }], candles), []);
});

test('null-valued points survive snapping so stale gaps stay visible', () => {
  assert.deepEqual(
    snapOverlayToCandles([{ t: 150, value: null }], [100, 200]),
    [{ t: 200, value: null }],
  );
});

test('snapping tolerates unsorted and duplicated candle times', () => {
  assert.deepEqual(
    snapOverlayToCandles([{ t: 150, value: 5 }], [300, 100, 200, 200, 100]),
    [{ t: 200, value: 5 }],
  );
});

test('two filings inside one candle collapse to that candle, latest winning', () => {
  const snapped = snapOverlayToCandles(
    [
      { t: 120, value: 1 },
      { t: 180, value: 2 },
    ],
    [100, 200],
  );

  assert.deepEqual(snapped, [{ t: 200, value: 1 }, { t: 200, value: 2 }]);
  // splitFinancialOverlaySegments de-dupes by time, keeping the later observation.
  assert.deepEqual(splitFinancialOverlaySegments(snapped), [[{ t: 200, value: 2 }]]);
});

test('an empty candle series yields no overlay rather than throwing', () => {
  assert.deepEqual(snapOverlayToCandles([{ t: 150, value: 5 }], []), []);
});
