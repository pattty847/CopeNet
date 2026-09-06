import assert from 'node:assert/strict';
import test from 'node:test';
import { setupVisualModel } from '../src/sections/market/forecasts/setupVisualModel';
import type { ForecastSetup } from '../src/sections/market/forecasts/types';
const setup: ForecastSetup = { kind: 'setup', direction: 'long', thesis: '', entry: { kind: 'limit', price: 100 },
  stop: 90, targets: [{ price: 120, fraction: 0.5 }, { price: 120.01, fraction: 0.5 }], zones: [], evidence: [] };
test('long setup maps exact price distances while separating adjacent target labels', () => {
  const model = setupVisualModel(setup);
  const first = model.levels.find((level) => level.label === 'Target 1')!;
  const second = model.levels.find((level) => level.label === 'Target 2')!;
  assert.equal(first.percent, 20);
  assert.equal(first.riskMultiple, 2);
  assert.ok(Math.abs(first.y - second.y) < 1);
  assert.equal(Math.abs(first.labelY - second.labelY), 56);
  assert.ok(model.targetY < model.entryY && model.entryY < model.stopY);
  assert.equal(model.levels.find((level) => level.kind === 'stop')!.riskMultiple, -1);
});
test('short setup shows lower prices as positive returns and the higher stop as risk', () => {
  const model = setupVisualModel({ ...setup, direction: 'short', stop: 110, targets: [{ price: 80, fraction: 1 }] });
  const target = model.levels.find((level) => level.kind === 'target')!;
  assert.equal(target.percent, 20);
  assert.equal(target.riskMultiple, 2);
  assert.ok(model.stopY < model.entryY && model.entryY < model.targetY);
  assert.equal(model.levels.find((level) => level.kind === 'stop')!.percent, -10);
});
