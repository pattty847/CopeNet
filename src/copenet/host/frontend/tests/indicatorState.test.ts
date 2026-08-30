// Indicator workspace state and its persisted contract.
//
// The persistence half matters more than it looks. This blob is written by one build and read
// by another, so the questions worth testing are all about the bad inputs: a layout from a
// version that no longer exists, an indicator that has since been retired, a hand-edited
// period well outside what the UI can produce, and a value that is simply corrupt.

import assert from 'node:assert/strict';
import test from 'node:test';

import { defaultConfig, normalizeConfig } from '../src/sections/market/indicators/config';
import { indicatorById, INDICATORS, searchIndicators } from '../src/sections/market/indicators/registry';
import {
  LAYOUT_VERSION,
  MAX_INDICATORS,
  addIndicator,
  configureIndicator,
  duplicateIndicator,
  moveIndicator,
  nextInstanceId,
  parseIndicatorLayout,
  removeIndicator,
  resetIndicator,
  setIndicatorVisibility,
  styleIndicator,
  type IndicatorInstance,
} from '../src/sections/market/indicators/state';

function stored(instances: unknown[], version = LAYOUT_VERSION): string {
  return JSON.stringify({ version, instances });
}

// ------------------------------------------------------------------ transitions

test('adding an indicator seeds it with the registry defaults and makes it visible', () => {
  const instances = addIndicator([], 'ema');
  assert.equal(instances.length, 1);
  assert.equal(instances[0].indicatorId, 'ema');
  assert.equal(instances[0].visible, true);
  assert.deepEqual(instances[0].config, defaultConfig(indicatorById('ema')!));
});

test('adding an unknown indicator is a no-op rather than a broken row', () => {
  assert.deepEqual(addIndicator([], 'not-an-indicator'), []);
});

test('instance ids are readable, unique, and reproducible without a clock or randomness', () => {
  let instances = addIndicator([], 'ema');
  instances = addIndicator(instances, 'ema');
  instances = addIndicator(instances, 'rsi');
  assert.deepEqual(instances.map((instance) => instance.instanceId), ['ema#1', 'ema#2', 'rsi#1']);
  // Removing the middle one frees its ordinal for reuse; ids stay short instead of climbing.
  const afterRemoval = removeIndicator(instances, 'ema#1');
  assert.equal(nextInstanceId('ema', afterRemoval), 'ema#1');
});

test('the layout is capped so a runaway loop cannot fill the chart', () => {
  let instances: IndicatorInstance[] = [];
  for (let i = 0; i < MAX_INDICATORS + 5; i += 1) instances = addIndicator(instances, 'sma');
  assert.equal(instances.length, MAX_INDICATORS);
});

test('configuring an indicator clamps the value to the bounds the registry declares', () => {
  const instances = configureIndicator(addIndicator([], 'ema'), 'ema#1', { period: 99_999 });
  assert.equal(instances[0].config.period, 400, 'a period beyond the maximum must be clamped, not stored');
  const negative = configureIndicator(instances, 'ema#1', { period: -5 });
  assert.equal(negative[0].config.period, 1);
});

test('configuring merges into the existing config rather than replacing it', () => {
  let instances = configureIndicator(addIndicator([], 'macd'), 'macd#1', { fast: 5 });
  instances = configureIndicator(instances, 'macd#1', { slow: 40 });
  assert.equal(instances[0].config.fast, 5);
  assert.equal(instances[0].config.slow, 40);
  assert.equal(instances[0].config.signal, 9, 'untouched inputs keep their defaults');
});

test('duplicating inserts directly after the source and copies its configuration', () => {
  let instances = addIndicator(addIndicator([], 'ema'), 'rsi');
  instances = configureIndicator(instances, 'ema#1', { period: 55 });
  instances = duplicateIndicator(instances, 'ema#1');
  assert.deepEqual(instances.map((instance) => instance.instanceId), ['ema#1', 'ema#2', 'rsi#1']);
  assert.equal(instances[1].config.period, 55);
  // A copy, not a shared reference — editing one must not edit the other.
  instances = configureIndicator(instances, 'ema#2', { period: 10 });
  assert.equal(instances[0].config.period, 55);
});

test('visibility, styling and reset each leave everything else alone', () => {
  let instances = configureIndicator(addIndicator([], 'ema'), 'ema#1', { period: 55 });
  instances = setIndicatorVisibility(instances, 'ema#1', false);
  assert.equal(instances[0].visible, false);
  assert.equal(instances[0].config.period, 55);

  instances = styleIndicator(instances, 'ema#1', 'value', { color: '#ff0000', lineWidth: 3 });
  assert.deepEqual(instances[0].styles?.value, { color: '#ff0000', lineWidth: 3 });

  instances = resetIndicator(instances, 'ema#1');
  assert.equal(instances[0].config.period, 20);
  assert.equal(instances[0].styles, undefined);
  assert.equal(instances[0].visible, true, 'reset restores a hidden indicator');
  assert.equal(instances[0].instanceId, 'ema#1', 'reset keeps the instance and its place');
});

test('moving an indicator is bounded at both ends', () => {
  const instances = addIndicator(addIndicator([], 'ema'), 'rsi');
  assert.deepEqual(moveIndicator(instances, 'ema#1', -1), instances, 'the first row cannot move up');
  assert.deepEqual(moveIndicator(instances, 'rsi#1', 1), instances, 'the last row cannot move down');
  assert.deepEqual(
    moveIndicator(instances, 'rsi#1', -1).map((instance) => instance.instanceId),
    ['rsi#1', 'ema#1'],
  );
});

test('every transition is pure — the input array is never mutated', () => {
  const original = addIndicator(addIndicator([], 'ema'), 'rsi');
  const snapshot = JSON.parse(JSON.stringify(original));
  configureIndicator(original, 'ema#1', { period: 99 });
  removeIndicator(original, 'ema#1');
  duplicateIndicator(original, 'ema#1');
  moveIndicator(original, 'ema#1', 1);
  resetIndicator(original, 'ema#1');
  setIndicatorVisibility(original, 'ema#1', false);
  styleIndicator(original, 'ema#1', 'value', { color: '#fff' });
  assert.deepEqual(original, snapshot);
});

// ------------------------------------------------------------------ persistence

test('a layout survives a save and load round trip', () => {
  let instances = configureIndicator(addIndicator([], 'ema'), 'ema#1', { period: 50, source: 'hlc3' });
  instances = styleIndicator(instances, 'ema#1', 'value', { color: '#8fb8e8', lineStyle: 'dashed' });
  instances = setIndicatorVisibility(addIndicator(instances, 'rsi'), 'rsi#1', false);
  assert.deepEqual(parseIndicatorLayout(stored(instances)), instances);
});

test('a layout from a different version is discarded rather than half-read', () => {
  const instances = addIndicator([], 'ema');
  assert.deepEqual(parseIndicatorLayout(stored(instances, LAYOUT_VERSION + 1)), []);
  assert.deepEqual(parseIndicatorLayout(stored(instances, LAYOUT_VERSION - 1)), []);
});

test('corrupt or absent storage falls back to an empty layout instead of throwing', () => {
  assert.deepEqual(parseIndicatorLayout(null), []);
  assert.deepEqual(parseIndicatorLayout(''), []);
  assert.deepEqual(parseIndicatorLayout('{not json'), []);
  assert.deepEqual(parseIndicatorLayout('[]'), []);
  assert.deepEqual(parseIndicatorLayout(JSON.stringify({ version: LAYOUT_VERSION })), []);
  assert.deepEqual(parseIndicatorLayout(JSON.stringify({ version: LAYOUT_VERSION, instances: 'nope' })), []);
});

test('a retired indicator is dropped without taking the rest of the layout with it', () => {
  const layout = stored([
    { instanceId: 'ema#1', indicatorId: 'ema', config: { period: 20 }, visible: true },
    { instanceId: 'gone#1', indicatorId: 'an-indicator-we-removed', config: {}, visible: true },
    { instanceId: 'rsi#1', indicatorId: 'rsi', config: { period: 14 }, visible: true },
  ]);
  const parsed = parseIndicatorLayout(layout);
  assert.deepEqual(parsed.map((instance) => instance.indicatorId), ['ema', 'rsi']);
});

test('a stored config outside the current bounds is repaired on load, not run', () => {
  // The case this exists for: a build where the maximum was higher, or a hand-edited blob.
  const parsed = parseIndicatorLayout(stored([
    { instanceId: 'ema#1', indicatorId: 'ema', config: { period: 5000, source: 'not-a-source' }, visible: true },
  ]));
  assert.equal(parsed[0].config.period, 400);
  assert.equal(parsed[0].config.source, 'close');
});

test('malformed rows are skipped and duplicate ids collapse', () => {
  const parsed = parseIndicatorLayout(stored([
    null,
    'string',
    { indicatorId: 'ema' },
    { instanceId: 'ema#1' },
    { instanceId: 'ema#1', indicatorId: 'ema', config: {}, visible: true },
    { instanceId: 'ema#1', indicatorId: 'sma', config: {}, visible: true },
  ]));
  assert.equal(parsed.length, 1);
  assert.equal(parsed[0].indicatorId, 'ema');
});

test('a stored layout longer than the cap is truncated on load', () => {
  const rows = Array.from({ length: MAX_INDICATORS + 20 }, (_, i) => ({
    instanceId: `sma#${i}`,
    indicatorId: 'sma',
    config: {},
    visible: true,
  }));
  assert.equal(parseIndicatorLayout(stored(rows)).length, MAX_INDICATORS);
});

test('a style that is not a colour, width or known dash pattern is dropped', () => {
  const parsed = parseIndicatorLayout(stored([{
    instanceId: 'ema#1',
    indicatorId: 'ema',
    config: {},
    visible: true,
    styles: {
      value: { color: 'javascript:alert(1)', lineWidth: 99, lineStyle: 'zigzag' },
      other: { color: '#8fb8e8' },
    },
  }]));
  assert.equal(parsed[0].styles?.value, undefined, 'no field of that style survived, so the entry goes');
  assert.deepEqual(parsed[0].styles?.other, { color: '#8fb8e8' });
});

test('visibility defaults to shown when the stored row does not say', () => {
  const parsed = parseIndicatorLayout(stored([{ instanceId: 'ema#1', indicatorId: 'ema', config: {} }]));
  assert.equal(parsed[0].visible, true);
});

// ------------------------------------------------------------------ registry

test('normalizeConfig fills every declared input for every indicator', () => {
  for (const definition of INDICATORS) {
    const config = normalizeConfig(definition, {});
    for (const input of definition.inputs) {
      assert.notEqual(config[input.key], undefined, `${definition.id} left ${input.key} unset`);
    }
  }
});

test('search matches on name, id and description without being fuzzy', () => {
  assert.ok(searchIndicators('rsi').some((definition) => definition.id === 'rsi'));
  assert.ok(searchIndicators('bollinger').some((definition) => definition.id === 'bbands'));
  assert.ok(searchIndicators('volume').some((definition) => definition.id === 'obv'));
  assert.equal(searchIndicators('zzzz').length, 0);
  assert.equal(searchIndicators('').length, INDICATORS.length);
});

test('every declared input has usable bounds and a default inside them', () => {
  for (const definition of INDICATORS) {
    for (const input of definition.inputs) {
      if (input.kind !== 'number') continue;
      assert.ok(input.min <= input.default && input.default <= input.max, `${definition.id}.${input.key}`);
      assert.ok(input.step > 0, `${definition.id}.${input.key} has no step`);
    }
    for (const input of definition.inputs) {
      if (input.kind !== 'enum') continue;
      assert.ok(
        input.choices.some((choice) => choice.value === input.default),
        `${definition.id}.${input.key} defaults to a choice it does not offer`,
      );
    }
  }
});
