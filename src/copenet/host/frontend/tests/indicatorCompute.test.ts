// The computation layer: full-history warm-up, range slicing, and memoisation.

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  barsPerYear,
  createIndicatorComputer,
  legendColor,
  legendOutputs,
} from '../src/sections/market/indicators/compute';
import { indicatorById } from '../src/sections/market/indicators/registry';
import { addIndicator, configureIndicator } from '../src/sections/market/indicators/state';
import { walkBars } from './indicatorFixtures';

const BARS = walkBars(500, 3);
const CONTEXT = { barsPerYear: 252 };

test('an indicator warms up over the full history, not over the visible window', () => {
  // The bug this prevents: computing over the visible bars restarts every warm-up, so
  // switching 5Y to 6M silently redraws the same EMA at different values.
  const computer = createIndicatorComputer();
  const instances = addIndicator([], 'ema');

  const windowed = computer.compute(BARS, 60, instances, CONTEXT)[0].outputs[0].points;
  const full = computer.compute(BARS, BARS.length, instances, CONTEXT)[0].outputs[0].points;
  assert.equal(windowed.length, 60);
  assert.deepEqual(windowed, full.slice(-60), 'the visible window must be a slice, not a recomputation');

  // And it genuinely differs from starting fresh at the window edge.
  const restarted = createIndicatorComputer().compute(BARS.slice(-60), 60, instances, CONTEXT)[0].outputs[0].points;
  assert.notEqual(restarted[0]?.value, windowed[0]?.value, 'a restarted warm-up would give a different first value');
  assert.ok(restarted.length < windowed.length, 'a restarted EMA loses its first 19 bars to warm-up');
});

test('an unrelated change recomputes nothing', () => {
  const definition = indicatorById('ema')!;
  const original = definition.compute;
  let calls = 0;
  definition.compute = (...args) => {
    calls += 1;
    return original(...args);
  };
  try {
    const computer = createIndicatorComputer();
    const instances = addIndicator([], 'ema');
    computer.compute(BARS, 200, instances, CONTEXT);
    assert.equal(calls, 1);
    // Re-render with the same bars and the same config — a popover opening, a hover, a
    // sibling indicator changing colour. None of it may reach the calculation.
    for (let i = 0; i < 5; i += 1) computer.compute(BARS, 200, instances, CONTEXT);
    assert.equal(calls, 1, 'the memo did not hold across identical renders');
    // Narrowing the range is a slice of the same computation, not a new one.
    computer.compute(BARS, 60, instances, CONTEXT);
    assert.equal(calls, 1, 'changing the visible range must not recompute');
    // Changing the configuration must.
    computer.compute(BARS, 60, configureIndicator(instances, 'ema#1', { period: 50 }), CONTEXT);
    assert.equal(calls, 2);
  } finally {
    definition.compute = original;
  }
});

test('two instances configured identically compute once between them', () => {
  const definition = indicatorById('sma')!;
  const original = definition.compute;
  let calls = 0;
  definition.compute = (...args) => {
    calls += 1;
    return original(...args);
  };
  try {
    const twins = addIndicator(addIndicator([], 'sma'), 'sma');
    const results = createIndicatorComputer().compute(BARS, 300, twins, CONTEXT);
    assert.equal(results.length, 2);
    assert.equal(calls, 1);
    assert.deepEqual(results[0].outputs[0].points, results[1].outputs[0].points);
  } finally {
    definition.compute = original;
  }
});

test('a new bar invalidates the memo — the cache keys on the series, not just the config', () => {
  const definition = indicatorById('rsi')!;
  const original = definition.compute;
  let calls = 0;
  definition.compute = (...args) => {
    calls += 1;
    return original(...args);
  };
  try {
    const computer = createIndicatorComputer();
    const instances = addIndicator([], 'rsi');
    computer.compute(BARS, 200, instances, CONTEXT);
    computer.compute([...BARS, { ...BARS[499], t: BARS[499].t + 86400 }], 200, instances, CONTEXT);
    assert.equal(calls, 2);
    // A revision of the last bar's close is also a change, even at the same length.
    const revised = [...BARS];
    revised[499] = { ...revised[499], c: revised[499].c + 1 };
    computer.compute(revised, 200, instances, CONTEXT);
    assert.equal(calls, 3);
  } finally {
    definition.compute = original;
  }
});

test('the memo is pruned to what is still on the chart', () => {
  // Without the sweep the cache grows by one entry per bar update per instance, forever.
  const definition = indicatorById('cci')!;
  const original = definition.compute;
  let calls = 0;
  definition.compute = (...args) => {
    calls += 1;
    return original(...args);
  };
  try {
    const computer = createIndicatorComputer();
    const instances = addIndicator([], 'cci');
    computer.compute(BARS, 200, instances, CONTEXT);
    computer.compute(BARS, 200, [], CONTEXT); // removed
    computer.compute(BARS, 200, instances, CONTEXT); // added back
    assert.equal(calls, 2, 'a removed indicator must not keep its entry alive');
  } finally {
    definition.compute = original;
  }
});

test('an indicator with no computable values in view is reported as short of history', () => {
  const computer = createIndicatorComputer();
  const instances = configureIndicator(addIndicator([], 'sma'), 'sma#1', { period: 400 });
  const [plenty] = computer.compute(BARS, BARS.length, instances, CONTEXT);
  assert.equal(plenty.insufficientHistory, false);

  const short = createIndicatorComputer().compute(BARS.slice(0, 30), 30, instances, CONTEXT)[0];
  assert.equal(short.insufficientHistory, true);
  assert.equal(short.outputs[0].points.length, 0);
  assert.equal(short.outputs[0].latest, null, 'no value means no legend reading, not a stale one');
});

test('the legend reading uses the definition\'s own formatter', () => {
  const computer = createIndicatorComputer();
  const rsi = computer.compute(BARS, 200, addIndicator([], 'rsi'), CONTEXT)[0];
  assert.match(rsi.outputs[0].latest!, /^\d+\.\d$/, 'RSI reads to one decimal');

  const adr = computer.compute(BARS, 200, addIndicator([], 'adr'), CONTEXT)[0];
  assert.match(adr.outputs[0].latest!, /%$/, 'a percentage series carries its unit');
});

test('styling overrides reach the drawn output without touching the values', () => {
  const computer = createIndicatorComputer();
  const instances = addIndicator([], 'ema');
  const plain = computer.compute(BARS, 200, instances, CONTEXT)[0].outputs[0];
  const styled = computer.compute(BARS, 200, [{ ...instances[0], styles: { value: { color: '#ff0000', lineWidth: 4, lineStyle: 'dotted' } } }], CONTEXT)[0].outputs[0];
  assert.equal(styled.color, '#ff0000');
  assert.equal(styled.lineWidth, 4);
  assert.equal(styled.lineStyle, 'dotted');
  assert.deepEqual(styled.points.map((point) => point.value), plain.points.map((point) => point.value));
});

test('the annualisation basis follows the chart interval', () => {
  assert.equal(barsPerYear('D'), 252);
  assert.equal(barsPerYear('W'), 52);
  assert.equal(barsPerYear('M'), 12);
});

test('changing the interval basis recomputes an interval-sensitive indicator', () => {
  const computer = createIndicatorComputer();
  const instances = addIndicator([], 'hv');
  const daily = computer.compute(BARS, 200, instances, { barsPerYear: 252 })[0].outputs[0].points.at(-1)!.value;
  const weekly = computer.compute(BARS, 200, instances, { barsPerYear: 52 })[0].outputs[0].points.at(-1)!.value;
  assert.ok(Math.abs(daily / weekly - Math.sqrt(252 / 52)) < 1e-9);
});

test('the legend reads lines before histograms, whatever order they are drawn in', () => {
  // MACD declares its histogram FIRST so the two lines paint over it. Reading order is the
  // opposite: a legend led by the histogram invites 0.54 to be read as the MACD value.
  const macd = createIndicatorComputer().compute(BARS, 200, addIndicator([], 'macd'), CONTEXT)[0];
  assert.deepEqual(macd.outputs.map((output) => output.key), ['histogram', 'macd', 'signal'], 'draw order');
  assert.deepEqual(legendOutputs(macd).map((output) => output.key), ['macd', 'signal', 'histogram'], 'reading order');
  assert.equal(legendColor(macd), macd.outputs.find((output) => output.key === 'macd')!.color);
});

test('a single-series indicator is unaffected by legend ordering', () => {
  const cmf = createIndicatorComputer().compute(BARS, 200, addIndicator([], 'cmf'), CONTEXT)[0];
  assert.deepEqual(legendOutputs(cmf).map((output) => output.key), ['cmf']);
  const bbands = createIndicatorComputer().compute(BARS, 200, addIndicator([], 'bbands'), CONTEXT)[0];
  assert.deepEqual(legendOutputs(bbands).map((output) => output.key), ['upper', 'middle', 'lower'], 'all lines keep declaration order');
});

test('an unknown indicator id in the layout is skipped rather than crashing the pass', () => {
  const computed = createIndicatorComputer().compute(
    BARS,
    200,
    [{ instanceId: 'x#1', indicatorId: 'retired', config: {}, visible: true }],
    CONTEXT,
  );
  assert.deepEqual(computed, []);
});
