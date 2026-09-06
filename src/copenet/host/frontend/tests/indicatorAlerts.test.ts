import assert from 'node:assert/strict';
import test from 'node:test';
import { alertCatalogue, evaluateAlertRequest, evaluateLatestRequest, evaluateOperand, validateOperand } from '../src/sections/market/indicators/alertEvaluator';
import { INDICATORS, indicatorById } from '../src/sections/market/indicators/registry';
import { defaultConfig } from '../src/sections/market/indicators/config';

const bars = Array.from({ length: 300 }, (_, i) => {
  const close = 100 + i / 4 + Math.sin(i / 3) * 10;
  return { t: 10000 + i * 86400, o: close - 1, h: close + 2, l: close - 2, c: close, v: 10000 + i };
});

test('alerts share chart formula and full-history outputs for every offered indicator', () => {
  for (const definition of INDICATORS) {
    const id = definition.id;
    for (const timeframe of [252, 52, 12]) {
      for (const output of definition.outputs) {
        const operand = validateOperand({ kind: 'indicator', indicatorId: id, config: defaultConfig(definition), output: output.key });
        assert.deepEqual(evaluateOperand(bars, operand, timeframe), definition.compute(bars, defaultConfig(definition), { barsPerYear: timeframe }).values[output.key]);
      }
    }
  }
});

test('alert catalogue comes from chart inputs and settings cannot silently clamp', () => {
  assert.deepEqual(alertCatalogue().map((item) => item.id), INDICATORS.map((definition) => definition.id));
  assert.throws(() => validateOperand({ kind: 'indicator', indicatorId: 'rsi', output: 'rsi', config: { period: 0 } }), /Invalid indicator setting/);
  assert.throws(() => validateOperand({ kind: 'indicator', indicatorId: 'rsi', output: 'unknown', config: {} }), /Invalid indicator output/);
});

test('alert evaluator preserves warmup nulls and rejects malformed candle input', () => {
  const request = { timeframe: 'weekly', bars: bars.slice(0, 3), left: { kind: 'indicator', indicatorId: 'rsi', output: 'rsi', config: {} }, right: { kind: 'constant', value: 30 } };
  const evaluated = evaluateAlertRequest(request);
  assert.ok('points' in evaluated);
  assert.equal(evaluated.points[0].left, null);
  assert.throws(() => evaluateAlertRequest({ ...request, bars: [{ ...bars[0], c: NaN }] }), /Invalid candle/);
  assert.throws(() => evaluateAlertRequest({ ...request, bars: [bars[1], bars[0]] }), /strictly ordered/);
});

const shifted = bars.map((bar) => ({ ...bar, o: bar.o * 1.5, h: bar.h * 1.5, l: bar.l * 1.5, c: bar.c * 1.5 }));

test('a batched latest value is the same number the chart draws on the final bar', () => {
  const { results } = evaluateLatestRequest({
    timeframe: 'weekly',
    requests: [
      { key: 'AAA', bars, indicators: [{ indicatorId: 'mama', config: {} }, { indicatorId: 'atr', config: {} }] },
      { key: 'BBB', bars: shifted, indicators: [{ indicatorId: 'mama', config: {} }] },
    ],
  });

  assert.deepEqual(results.map((row) => row.key), ['AAA', 'BBB']);
  for (const [row, source] of [[results[0], bars], [results[1], shifted]] as const) {
    assert.equal(row.error, null);
    assert.equal(row.t, source[source.length - 1].t);
    for (const [id, outputs] of Object.entries(row.values)) {
      const definition = indicatorById(id)!;
      const chart = definition.compute(source, defaultConfig(definition), { barsPerYear: 52 }).values;
      for (const [output, value] of Object.entries(outputs)) {
        assert.equal(value, chart[output][source.length - 1] ?? null);
      }
    }
  }
});

test('batching a symbol does not change its regime versus evaluating it alone', () => {
  const operand = { kind: 'indicator', indicatorId: 'mama', config: {} };
  const pair = evaluateAlertRequest({ action: 'evaluate', timeframe: 'weekly', bars,
    left: { ...operand, output: 'mama' }, right: { ...operand, output: 'fama' } });
  assert.ok('points' in pair);
  const alone = pair.points[pair.points.length - 1];

  const { results } = evaluateLatestRequest({ timeframe: 'weekly',
    requests: [{ key: 'X', bars: shifted, indicators: [{ indicatorId: 'mama', config: {} }] },
               { key: 'AAA', bars, indicators: [{ indicatorId: 'mama', config: {} }] }] });
  const batched = results.find((row) => row.key === 'AAA')!.values.mama;

  assert.equal(batched.mama, alone.left);
  assert.equal(batched.fama, alone.right);
});

test('one malformed symbol reports its own error instead of voiding the batch', () => {
  const { results } = evaluateLatestRequest({
    timeframe: 'weekly',
    requests: [
      { key: 'GOOD', bars, indicators: [{ indicatorId: 'mama', config: {} }] },
      { key: 'UNORDERED', bars: [bars[1], bars[0]], indicators: [{ indicatorId: 'mama', config: {} }] },
      { key: 'UNKNOWN', bars, indicators: [{ indicatorId: 'nope', config: {} }] },
      { key: 'ALSO_GOOD', bars: shifted, indicators: [{ indicatorId: 'mama', config: {} }] },
    ],
  });

  assert.equal(results.length, 4);
  assert.equal(results[0].error, null);
  assert.match(results[1].error!, /strictly ordered/);
  assert.match(results[2].error!, /Unsupported indicator/);
  assert.equal(results[3].error, null);
  assert.notEqual(results[3].values.mama.mama, null);
});

test('the batch rejects an oversized or empty symbol list rather than truncating it', () => {
  assert.throws(() => evaluateLatestRequest({ timeframe: 'weekly', requests: [] }), /1-1000 symbol requests/);
  assert.throws(() => evaluateLatestRequest({ timeframe: 'yearly',
    requests: [{ key: 'A', bars, indicators: [{ indicatorId: 'mama', config: {} }] }] }), /Unsupported timeframe/);
});

test('the same indicator twice in one request keeps its readings apart', () => {
  const { results } = evaluateLatestRequest({
    timeframe: 'daily',
    requests: [{ key: 'A', bars, indicators: [
      { indicatorId: 'sma', config: { period: 50 }, label: 'ma50' },
      { indicatorId: 'sma', config: { period: 200 }, label: 'ma200' },
    ] }],
  });
  const values = results[0].values;
  const fifty = indicatorById('sma')!.compute(bars, { period: 50, source: 'close' }, { barsPerYear: 252 }).values.value;
  const two = indicatorById('sma')!.compute(bars, { period: 200, source: 'close' }, { barsPerYear: 252 }).values.value;

  assert.equal(values.ma50.value, fifty[bars.length - 1]);
  assert.equal(values.ma200.value, two[bars.length - 1]);
  assert.notEqual(values.ma50.value, values.ma200.value);

  // Unlabelled duplicates would both key on 'sma'. That must be refused, not resolved
  // by last-write-wins, which would return the 200-day average under both names.
  const collided = evaluateLatestRequest({ timeframe: 'daily', requests: [{ key: 'A', bars,
    indicators: [{ indicatorId: 'sma', config: { period: 50 } }, { indicatorId: 'sma', config: { period: 200 } }] }] });
  assert.match(collided.results[0].error!, /labels must be unique/);
});
