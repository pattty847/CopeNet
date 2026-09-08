import assert from 'node:assert/strict';
import test from 'node:test';
import { setupVisualModel } from '../src/sections/market/forecasts/setupVisualModel';
import type { ForecastChart, ForecastSetup } from '../src/sections/market/forecasts/types';
const setup: ForecastSetup = { kind: 'setup', direction: 'long', thesis: '', entry: { kind: 'limit', price: 100 },
  stop: 90, targets: [{ price: 120, fraction: 0.5 }, { price: 120.01, fraction: 0.5 }], zones: [], evidence: [] };
const chart: ForecastChart = { publishedAt: 10000000, deadlineAt: 14838400, history: [{ t: 7408000, close: 98 }, { t: 9900000, close: 101 }], outcome: [], health: 'ready', reason: null, basis: 'publication', historyAvailable: true };
test('long setup maps exact price distances while separating adjacent target labels', () => {
  const model = setupVisualModel(setup, chart);
  const first = model.levels.find((level) => level.label === 'T1')!;
  const second = model.levels.find((level) => level.label === 'T2')!;
  assert.equal(first.percent, 20);
  assert.equal(first.riskMultiple, 2);
  assert.ok(Math.abs(first.y - second.y) < 1);
  assert.equal(Math.abs(first.labelY - second.labelY), 14);
  assert.ok(model.targetY < model.entryY && model.entryY < model.stopY);
  assert.equal(model.levels.find((level) => level.kind === 'stop')!.riskMultiple, -1);
});
test('short setup shows lower prices as positive returns and the higher stop as risk', () => {
  const model = setupVisualModel({ ...setup, direction: 'short', stop: 110, targets: [{ price: 80, fraction: 1 }] }, chart);
  const target = model.levels.find((level) => level.kind === 'target')!;
  assert.equal(target.percent, 20);
  assert.equal(target.riskMultiple, 2);
  assert.ok(model.stopY < model.entryY && model.entryY < model.targetY);
  assert.equal(model.levels.find((level) => level.kind === 'stop')!.percent, -10);
});

test('future space has no invented path and real outcomes extend only to observed closes', () => {
  assert.equal(setupVisualModel(setup, chart).outcomePath, '');
  const observed = { ...chart, outcome: [{ t: chart.publishedAt + 86400, close: 103 }] };
  const model = setupVisualModel(setup, observed);
  assert.ok(model.outcomePath.endsWith(`${model.x(observed.outcome[0].t)},${model.y(103)}`));
  assert.ok(model.x(observed.outcome[0].t) < model.right);
  assert.equal(model.points.length, 3);
});
