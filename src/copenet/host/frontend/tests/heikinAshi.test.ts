import assert from 'node:assert/strict';
import test from 'node:test';

import { candleRows, heikinAshi } from '../src/sections/market/heikinAshi';
import type { Ohlcv } from '../src/sections/market/types';

function bar(t: number, o: number, h: number, l: number, c: number, v = 1000): Ohlcv {
  return { t, o, h, l, c, v };
}

/** A deliberately jagged series: gaps up, gaps down, an inside bar and a doji. */
const SERIES: Ohlcv[] = [
  bar(1, 10, 12, 9, 11),
  bar(2, 11, 15, 10, 14),
  bar(3, 16, 18, 15, 15),
  bar(4, 15, 15.5, 12, 12.5),
  bar(5, 12, 13, 11, 13),
  bar(6, 13, 13, 13, 13),
];

test('close is the bar own average and open is the midpoint of the previous synthetic bar', () => {
  const ha = heikinAshi(SERIES);

  assert.equal(ha[0].c, (10 + 12 + 9 + 11) / 4);
  // The first bar has no predecessor, so it seeds from its own real open and close.
  assert.equal(ha[0].o, (10 + 11) / 2);
  assert.equal(ha[1].o, (ha[0].o + ha[0].c) / 2);
  assert.equal(ha[1].c, (11 + 15 + 10 + 14) / 4);
});

test('the high and low contain the synthetic body', () => {
  for (const candle of heikinAshi(SERIES)) {
    assert.ok(candle.h >= Math.max(candle.o, candle.c), `high ${candle.h} clips the body`);
    assert.ok(candle.l <= Math.min(candle.o, candle.c), `low ${candle.l} clips the body`);
    assert.ok(candle.h >= candle.l);
  }
});

test('timestamps and volume pass through untouched', () => {
  const ha = heikinAshi(SERIES);

  assert.deepEqual(ha.map((candle) => candle.t), SERIES.map((candle) => candle.t));
  assert.deepEqual(ha.map((candle) => candle.v), SERIES.map((candle) => candle.v));
});

test('the transform is causal, so truncating the end leaves earlier bars identical', () => {
  // This is what replay does. If it were not causal, stepping the cursor would silently
  // redraw history behind it.
  const full = heikinAshi(SERIES);
  const truncated = heikinAshi(SERIES.slice(0, 4));

  assert.deepEqual(truncated, full.slice(0, 4));
});

test('a wrong seed decays by exactly half a bar at a time', () => {
  // Why warm-up matters, and how much of it is enough. `open[i] = (open[i-1] + close[i-1])/2`
  // carries the previous open at weight one half, so an error in the seed halves every bar.
  // Computing over a range-sliced array therefore visibly changes the candles near the cut —
  // which is a chart redrawing history when the operator switches 6M to 1Y — while a long
  // warm-up drives the error below float precision and makes the seed irrelevant.
  const series: Ohlcv[] = [];
  let price = 100;
  for (let index = 0; index < 20; index += 1) {
    const close = price * (1 + (((index * 37) % 7) - 3) / 100);
    series.push(bar(index + 1, price, Math.max(price, close) * 1.01, Math.min(price, close) * 0.99, close));
    price = close;
  }

  const warmed = heikinAshi(series).slice(10);
  const reseeded = heikinAshi(series.slice(10));
  const deltas = warmed.map((candle, index) => Math.abs(candle.o - reseeded[index].o));

  assert.ok(deltas[0] > 0.5, `the seed should matter at the cut, was ${deltas[0]}`);
  for (let index = 1; index < 5; index += 1) {
    assert.ok(
      Math.abs(deltas[index] / deltas[index - 1] - 0.5) < 1e-9,
      `error should halve each bar, bar ${index} moved by ${deltas[index] / deltas[index - 1]}`,
    );
  }
});

test('candleRows warms up over full history and returns only the visible tail', () => {
  const visible = 3;

  const rows = candleRows(SERIES, visible, 'heikin-ashi');

  assert.equal(rows.length, visible);
  // Identical to computing over everything and slicing — the whole point of the helper.
  assert.deepEqual(rows, heikinAshi(SERIES).slice(SERIES.length - visible));
});

test('the plain style returns the real bars unchanged', () => {
  const rows = candleRows(SERIES, 3, 'candles');

  assert.deepEqual(rows, SERIES.slice(3));
});

test('both styles return the same length so the candle series stays index-aligned with bars', () => {
  for (const visible of [0, 1, 3, SERIES.length, SERIES.length + 5]) {
    assert.equal(
      candleRows(SERIES, visible, 'heikin-ashi').length,
      candleRows(SERIES, visible, 'candles').length,
      `visible=${visible} drifted`,
    );
  }
});

test('an empty series produces an empty series rather than throwing', () => {
  assert.deepEqual(heikinAshi([]), []);
  assert.deepEqual(candleRows([], 5, 'heikin-ashi'), []);
});

test('a flat bar produces a flat synthetic bar, not a divide-by-zero artifact', () => {
  const ha = heikinAshi([bar(1, 13, 13, 13, 13)]);

  assert.equal(ha[0].o, 13);
  assert.equal(ha[0].c, 13);
  assert.equal(ha[0].h, 13);
  assert.equal(ha[0].l, 13);
});

test('every synthetic value is finite for a realistic series', () => {
  for (const candle of heikinAshi(SERIES)) {
    for (const key of ['o', 'h', 'l', 'c'] as const) {
      assert.ok(Number.isFinite(candle[key]), `${key} was not finite`);
    }
  }
});
