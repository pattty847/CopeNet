import assert from 'node:assert/strict';
import test from 'node:test';
import type { ChartObject } from '../src/sections/market/chartAgent/types';
import type { Ohlcv } from '../src/sections/market/types';
import { projectDrawing } from '../src/sections/market/drawings/geometry';
import { anchoredVwapValues, avwapColumnNames, colorName, readDrawings } from '../src/sections/market/drawings/reads';

// Irregular timestamps on purpose: a weekend gap must count as one bar, never three days.
const TIMES = [100, 200, 300, 600, 700, 800, 1100, 1200, 1300, 1400];
const bars: Ohlcv[] = TIMES.map((t, index) => ({ t, o: 50 + index, h: 53 + index, l: 49 + index, c: 52 + index, v: 1000 + index * 100 }));
const SLOT = 12;

function drawing(kind: ChartObject['kind'], anchors: ChartObject['anchors'], extra: Partial<ChartObject> = {}): ChartObject {
  return { id: kind, kind, anchors, timeframe: 'D', label: '', color: '#e5484d', visible: true, rationale: '', evidence: [], owner: { kind: 'operator' }, ...extra };
}

function chart(logScale: boolean) {
  const toY = (price: number) => logScale ? 400 - Math.log(price) * 80 : 400 - price * 3;
  const toPrice = (y: number) => logScale ? Math.exp((400 - y) / 80) : (400 - y) / 3;
  const projection = { width: SLOT * (TIMES.length - 1), height: 400, price: toY,
    time: (time: number) => { const index = TIMES.indexOf(time); return index < 0 ? null : index * SLOT; } };
  return { projection, toPrice };
}

for (const logScale of [false, true]) {
  test(`atLast is the price under the painted line at the latest candle (${logScale ? 'log' : 'linear'} axis)`, () => {
    const { projection, toPrice } = chart(logScale);
    const line = drawing('extended_trendline', [{ t: 200, value: 50 }, { t: 700, value: 58 }]);
    const [start, end] = projectDrawing(line, projection)!.lines![0].points;
    const lastX = (TIMES.length - 1) * SLOT;
    const paintedY = start.y + ((end.y - start.y) * (lastX - start.x)) / (end.x - start.x);

    const [read] = readDrawings([line], bars, { timeframe: 'D', logScale });

    assert.ok(Math.abs(read.atLast! - toPrice(paintedY)) < 1e-6, `${read.atLast} vs painted ${toPrice(paintedY)}`);
    // The model's own projection formula has to land on the same line one anchor later.
    const barsFromLast = 4 - (TIMES.length - 1);
    const projected = logScale ? read.atLast! * (1 + read.perBarPct! / 100) ** barsFromLast : read.atLast! + read.perBar! * barsFromLast;
    assert.ok(Math.abs(projected - 58) < 1e-6);
    assert.equal(logScale ? read.perBar : read.perBarPct, undefined, 'only the slope that matches the axis is reported');
  });
}

test('slope counts candles, so a gap in time does not bend the line', () => {
  const [read] = readDrawings([drawing('ray', [{ t: 300, value: 60 }, { t: 600, value: 61 }])], bars, { timeframe: 'D', logScale: false });
  assert.equal(read.perBar, 1);
  assert.equal(read.extends, 'right');
});

test('each kind reports the facts a person reads off it', () => {
  const close = bars[bars.length - 1].c;
  const reads = readDrawings([
    drawing('level', [{ t: 300, value: 50 }]),
    drawing('zone', [{ t: 100, value: 40 }, { t: 300, value: 45 }]),
    drawing('fib_retracement', [{ t: 100, value: 100 }, { t: 300, value: 50 }]),
    drawing('position', [{ t: 100, value: 50 }, { t: 300, value: 60 }, { t: 300, value: 45 }]),
    drawing('measurement', [{ t: 100, value: 50 }, { t: 600, value: 55 }]),
  ], bars, { timeframe: 'D', logScale: false });
  const by = Object.fromEntries(reads.map((read) => [read.kind, read]));
  assert.equal(by.level.atLast, 50);
  assert.ok(Math.abs(by.level.vsClosePct! - ((close - 50) / 50) * 100) < 1e-9);
  assert.equal(by.zone.detail, 'close above zone');
  assert.ok(by.fib_retracement.detail!.startsWith('0=100.00|0.236=88.20|'), by.fib_retracement.detail);
  assert.ok(by.position.detail!.includes('long') && by.position.detail!.includes('R:R=2.00'));
  assert.equal(by.measurement.detail, '5.00 (10.0%) over 3 bars');
});

test('only painted drawings are read: hidden, other-timeframe and out-of-range ones never invent values', () => {
  const reads = readDrawings([
    drawing('level', [{ t: 300, value: 50 }], { id: 'hidden', visible: false }),
    drawing('level', [{ t: 300, value: 50 }], { id: 'weekly', timeframe: 'W' }),
    drawing('trendline', [{ t: 5, value: 50 }, { t: 300, value: 55 }], { id: 'old' }),
  ], bars, { timeframe: 'D', logScale: false });
  assert.deepEqual(reads.map((read) => read.id), ['old']);
  assert.equal(reads[0].atLast, undefined);
  assert.match(reads[0].detail!, /outside the loaded range/);
});

test('an anchor in the reserved future whitespace still has a bar position', () => {
  const future = 1400 + 100 * 3;
  const [read] = readDrawings([drawing('trendline', [{ t: 1400, value: 61 }, { t: future, value: 64 }])], bars, { timeframe: 'D', logScale: false });
  assert.equal(read.perBar, 1);
  assert.equal(read.atLast, 61);
});

test('anchored VWAP is null before its anchor, matches the cumulative definition, and names its table column', () => {
  const first = drawing('avwap', [{ t: 600, value: 0 }], { id: 'a' });
  const second = drawing('avwap', [{ t: 1100, value: 0 }], { id: 'b' });
  const values = anchoredVwapValues(first, bars);
  assert.deepEqual(values.slice(0, 3), [null, null, null]);
  const typical = (bar: Ohlcv) => (bar.h + bar.l + bar.c) / 3;
  const expected = (typical(bars[3]) * bars[3].v + typical(bars[4]) * bars[4].v) / (bars[3].v + bars[4].v);
  assert.ok(Math.abs(values[4]! - expected) < 1e-9);
  assert.deepEqual([...avwapColumnNames([first, second], 'D')], [['a', 'avwap'], ['b', 'avwap@avwap#2']]);
  const reads = readDrawings([first, second], bars, { timeframe: 'D', logScale: false });
  assert.equal(reads[1].detail, 'series in table column avwap@avwap#2');
  assert.equal(reads[0].atLast, values[values.length - 1]);
});

test('the operator says "the red line", so a custom hex still resolves to a colour word', () => {
  assert.equal(colorName('#e5484d'), 'red');
  assert.equal(colorName('#ff2020'), 'red');
  assert.equal(colorName('#3b9eff'), 'blue');
});

test('anchored VWAP bands: a standard-deviation band is symmetric, a percent band is a fixed share, and the source is honored', async () => {
  const { anchoredVwap } = await import('../src/sections/market/drawings/reads');
  const study = drawing('avwap', [{ t: 100, value: 0 }], { params: { band1: 2, source: 'close' } });
  const { values, bands } = anchoredVwap(study, bars);
  assert.equal(values[0], bars[0].c, 'close source');
  const last = values.length - 1;
  assert.ok(Math.abs((bands[0].upper[last]! - values[last]!) - (values[last]! - bands[0].lower[last]!)) < 1e-9);
  assert.ok(bands[0].upper[last]! > values[last]!);
  const percent = anchoredVwap(drawing('avwap', [{ t: 100, value: 0 }], { params: { band1: 5, bandMode: 'percent' } }), bars);
  assert.ok(Math.abs(percent.bands[0].upper[last]! - percent.values[last]! * 1.05) < 1e-9);
  assert.equal(anchoredVwap(drawing('avwap', [{ t: 100, value: 0 }]), bars).bands.length, 0, 'no params is the classic study');
});
