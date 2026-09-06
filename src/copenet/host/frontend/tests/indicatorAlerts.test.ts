import assert from 'node:assert/strict';
import test from 'node:test';
import { alertCatalogue, evaluateAlertRequest, evaluateOperand, validateOperand } from '../src/sections/market/indicators/alertEvaluator';
import { INDICATORS } from '../src/sections/market/indicators/registry';
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
  assert.equal(evaluateAlertRequest(request).points?.[0].left, null);
  assert.throws(() => evaluateAlertRequest({ ...request, bars: [{ ...bars[0], c: NaN }] }), /Invalid candle/);
  assert.throws(() => evaluateAlertRequest({ ...request, bars: [bars[1], bars[0]] }), /strictly ordered/);
});
