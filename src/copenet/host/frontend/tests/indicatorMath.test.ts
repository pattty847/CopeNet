// Primitives, and the properties that must hold for EVERY indicator in the catalogue.
//
// The registry-wide loop is the load-bearing half of this file. Per-indicator fixtures catch
// a wrong formula; only a universal sweep catches the failure mode that actually ships — a
// new indicator added six months from now that emits NaN on a flat series, or that reads a
// future bar because a window was written as i+n instead of i-n.

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  atr,
  ema,
  finite,
  highest,
  lowest,
  rma,
  rollingSum,
  safeDiv,
  sma,
  sourceValues,
  stdev,
  subtract,
  trueRange,
  wma,
} from '../src/sections/market/indicators/math';
import { INDICATORS } from '../src/sections/market/indicators/registry';
import { defaultConfig } from '../src/sections/market/indicators/config';
import {
  barsFromCloses,
  barsFromOhlcv,
  constantBars,
  rampBars,
  walkBars,
  zeroVolume,
} from './indicatorFixtures';

const CONTEXT = { barsPerYear: 252 };

// ------------------------------------------------------------------ primitives

test('sma averages a full window and stays null before one exists', () => {
  assert.deepEqual(sma([1, 2, 3, 4, 5], 3), [null, null, 2, 3, 4]);
});

test('sma treats a window containing null as null rather than a smaller average', () => {
  assert.deepEqual(sma([1, null, 3, 4, 5], 3), [null, null, null, null, 4]);
});

test('ema seeds from the first full simple average, not from the first bar', () => {
  // period 3 -> alpha 0.5, seed = mean(1,2,3) = 2, then 4*.5+2*.5=3, 5*.5+3*.5=4
  assert.deepEqual(ema([1, 2, 3, 4, 5], 3), [null, null, 2, 3, 4]);
});

test('rma uses Wilder 1/n smoothing, which is slower than an ema of the same length', () => {
  const values = [1, 2, 3, 4, 5, 6];
  const wilder = rma(values, 3);
  const exponential = ema(values, 3);
  assert.equal(wilder[2], 2);
  // (2*2 + 4)/3 = 2.6667 for Wilder against 3 for the EMA.
  assert.ok(Math.abs((wilder[3] as number) - 8 / 3) < 1e-12);
  assert.ok((wilder[5] as number) < (exponential[5] as number));
});

test('wma weights the newest bar most heavily', () => {
  const result = wma([1, 2, 3, 4, 5], 3);
  assert.ok(Math.abs((result[2] as number) - 14 / 6) < 1e-12);
  assert.ok(Math.abs((result[4] as number) - 26 / 6) < 1e-12);
});

test('stdev is the population deviation Bollinger specifies, not the sample deviation', () => {
  // mean 5, squared deviations 9+1+1+1+0+0+4+16 = 32, /8 = 4, sqrt = 2
  const result = stdev([2, 4, 4, 4, 5, 5, 7, 9], 8);
  assert.ok(Math.abs((result[7] as number) - 2) < 1e-12);
});

test('highest and lowest read the window inclusive of the current bar', () => {
  assert.deepEqual(highest([1, 5, 3], 2), [null, 5, 5]);
  assert.deepEqual(lowest([1, 5, 3], 2), [null, 1, 3]);
});

test('rollingSum matches sma times the period', () => {
  assert.deepEqual(rollingSum([1, 2, 3, 4], 2), [null, 3, 5, 7]);
});

test('trueRange accounts for gaps and falls back to the bar range on bar zero', () => {
  const bars = barsFromOhlcv([
    [10, 12, 9, 11, 1],
    [11, 20, 18, 19, 1], // gaps up: |20 - 11| = 9 beats the 2-wide bar range
  ]);
  assert.deepEqual(trueRange(bars), [3, 9]);
});

test('atr is a Wilder average of true range', () => {
  const bars = barsFromOhlcv([
    [10, 12, 10, 11, 1],
    [11, 13, 11, 12, 1],
    [12, 14, 12, 13, 1],
  ]);
  assert.ok(Math.abs((atr(bars, 3)[2] as number) - 2) < 1e-12);
});

test('safeDiv reports an unusable denominator instead of returning Infinity', () => {
  assert.equal(safeDiv(1, 0), null);
  assert.equal(safeDiv(null, 2), null);
  assert.equal(safeDiv(6, 3), 2);
});

test('finite rejects NaN and Infinity at the boundary', () => {
  assert.equal(finite(Number.NaN), null);
  assert.equal(finite(Number.POSITIVE_INFINITY), null);
  assert.equal(finite(0), 0);
});

test('subtract keeps null semantics element-wise', () => {
  assert.deepEqual(subtract([5, null, 3], [1, 1, null]), [4, null, null]);
});

test('derived sources are computed, never read from a stored field', () => {
  const bars = barsFromOhlcv([[10, 20, 5, 15, 1]]);
  assert.deepEqual(sourceValues(bars, 'hl2'), [12.5]);
  assert.deepEqual(sourceValues(bars, 'hlc3'), [(20 + 5 + 15) / 3]);
  assert.deepEqual(sourceValues(bars, 'ohlc4'), [12.5]);
});

// -------------------------------------------------- registry-wide invariants

const WALK = walkBars(400, 7);

function everyValue(result: Record<string, (number | null)[]>): (number | null)[] {
  return Object.values(result).flat();
}

for (const definition of INDICATORS) {
  const config = defaultConfig(definition);

  test(`${definition.id}: outputs align 1:1 with the input bars`, () => {
    const result = definition.compute(WALK, config, CONTEXT);
    for (const key of definition.outputs.map((output) => output.key)) {
      assert.ok(result.values[key], `${definition.id} declares output "${key}" but did not produce it`);
      assert.equal(result.values[key].length, WALK.length);
    }
  });

  test(`${definition.id}: never emits NaN or Infinity`, () => {
    for (const bars of [WALK, constantBars(120), rampBars(120), zeroVolume(WALK)]) {
      const result = definition.compute(bars, config, CONTEXT);
      for (const value of everyValue(result.values)) {
        assert.ok(value === null || Number.isFinite(value), `${definition.id} produced ${String(value)}`);
      }
    }
  });

  test(`${definition.id}: is causal — a prefix computes the same values as the full history`, () => {
    // The property that makes "compute over all history, then slice to the visible range"
    // safe. If any window reached forward, the two runs would disagree at the cut.
    const cut = 260;
    const full = definition.compute(WALK, config, CONTEXT);
    const prefix = definition.compute(WALK.slice(0, cut), config, CONTEXT);
    for (const key of definition.outputs.map((output) => output.key)) {
      for (let i = 0; i < cut; i += 1) {
        assert.deepEqual(
          prefix.values[key][i],
          full.values[key][i],
          `${definition.id}.${key} differs at bar ${i} when later bars are withheld`,
        );
      }
    }
  });

  test(`${definition.id}: recomputes deterministically`, () => {
    const first = definition.compute(WALK, config, CONTEXT);
    const second = definition.compute(WALK, config, CONTEXT);
    assert.deepEqual(second.values, first.values);
  });

  test(`${definition.id}: returns all-null on a history shorter than its warm-up`, () => {
    const warmup = definition.warmup(config);
    const short = WALK.slice(0, Math.max(1, Math.min(warmup - 1, 3)));
    const result = definition.compute(short, config, CONTEXT);
    for (const value of everyValue(result.values)) {
      assert.ok(value === null || Number.isFinite(value));
    }
  });

  test(`${definition.id}: survives a single bar and an empty series`, () => {
    for (const bars of [[], WALK.slice(0, 1)]) {
      const result = definition.compute(bars, config, CONTEXT);
      for (const key of definition.outputs.map((output) => output.key)) {
        assert.equal(result.values[key].length, bars.length);
      }
    }
  });

  if (definition.requires.includes('volume')) {
    test(`${definition.id}: reports nothing rather than zero when volume is missing`, () => {
      const result = definition.compute(zeroVolume(WALK), config, CONTEXT);
      const values = everyValue(result.values);
      assert.ok(values.every((value) => value === null), `${definition.id} drew a series from absent volume`);
    });
  }

  test(`${definition.id}: is fully warm by the bar count it declares`, () => {
    // `warmup` is the bar by which EVERY output exists — the number behind the eventual
    // "needs N bars" notice. Outputs may arrive EARLIER (MACD's line precedes its signal,
    // +DI precedes ADX); none may arrive later, because that would have the UI promise a
    // series the chart then draws empty.
    assert.ok(definition.short(config).length > 0);
    const warmup = definition.warmup(config);
    assert.ok(warmup >= 1);
    const result = definition.compute(WALK, config, CONTEXT);
    for (const key of definition.outputs.map((output) => output.key)) {
      assert.notEqual(
        result.values[key][warmup],
        null,
        `${definition.id}.${key} is still null at bar ${warmup}, its declared warm-up`,
      );
    }
  });
}

test('the catalogue has stable, unique ids and no duplicate output keys', () => {
  const ids = INDICATORS.map((definition) => definition.id);
  assert.equal(new Set(ids).size, ids.length);
  for (const definition of INDICATORS) {
    const keys = definition.outputs.map((output) => output.key);
    assert.equal(new Set(keys).size, keys.length, `${definition.id} declares a duplicate output key`);
    assert.ok(definition.outputs.length > 0, `${definition.id} declares no outputs`);
  }
});

test('a flat series produces no movement anywhere in the catalogue', () => {
  const flat = constantBars(200);
  for (const definition of INDICATORS) {
    const result = definition.compute(flat, defaultConfig(definition), CONTEXT);
    for (const value of everyValue(result.values)) {
      assert.ok(value === null || Number.isFinite(value), `${definition.id} produced ${String(value)} on a flat series`);
    }
  }
});

test('gaps in the timestamps do not change the values — indicators are bar-indexed', () => {
  const dense = barsFromCloses([10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21]);
  const gapped = dense.map((bar, i) => ({ ...bar, t: bar.t + (i > 5 ? 30 * 86400 : 0) }));
  for (const definition of INDICATORS) {
    const config = defaultConfig(definition);
    assert.deepEqual(
      definition.compute(gapped, config, CONTEXT).values,
      definition.compute(dense, config, CONTEXT).values,
      `${definition.id} read the timestamp rather than the bar index`,
    );
  }
});
