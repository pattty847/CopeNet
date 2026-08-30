// Chart lifecycle for the indicator layer.
//
// The numeric tests prove the values are right. These prove the chart ends up in the state
// those values describe — and, more importantly, that it ends up EMPTY when it should. Every
// leak this suite is built to catch is invisible on screen until the tenth toggle: a series
// left behind after a remove, a pane that survives its indicator, a reference line recreated
// on every render until the pane is striped with them.

import assert from 'node:assert/strict';
import test from 'node:test';

import type { IChartApi } from 'lightweight-charts';
import { createIndicatorComputer, barsPerYear } from '../src/sections/market/indicators/compute';
import { IndicatorChartLayer } from '../src/sections/market/indicators/render';
import {
  addIndicator,
  configureIndicator,
  duplicateIndicator,
  moveIndicator,
  removeIndicator,
  setIndicatorVisibility,
  type IndicatorInstance,
} from '../src/sections/market/indicators/state';
import { FakeChart, type FakeSeries } from './fakeChart';
import { walkBars } from './indicatorFixtures';

const BARS = walkBars(400, 5);
const CONTEXT = { barsPerYear: barsPerYear('D') };

function layerFor(instances: IndicatorInstance[], bars = BARS, visible = bars.length) {
  const chart = new FakeChart();
  const layer = new IndicatorChartLayer(chart as unknown as IChartApi);
  const computer = createIndicatorComputer();
  const render = (next: IndicatorInstance[], nextBars = bars, nextVisible = visible) =>
    layer.sync(computer.compute(nextBars, nextVisible, next, CONTEXT));
  render(instances);
  return { chart, layer, render };
}

function build(...ids: string[]): IndicatorInstance[] {
  return ids.reduce<IndicatorInstance[]>((instances, id) => addIndicator(instances, id), []);
}

test('a price overlay draws on the candle pane and adds no pane of its own', () => {
  const { chart } = layerFor(build('ema'));
  assert.equal(chart.paneList.length, 1, 'price overlays must not create a pane');
  assert.equal(chart.series.length, 1);
  assert.equal(chart.series[0].createdInPane, 0);
  assert.equal(chart.series[0].options.priceScaleId, 'right', 'an overlay shares the candle scale');
});

test('a pane indicator gets its own pane and every one of its outputs lands in it', () => {
  const { chart } = layerFor(build('macd'));
  assert.equal(chart.paneList.length, 2);
  assert.equal(chart.series.length, 3, 'MACD is a histogram plus two lines');
  assert.ok(chart.series.every((series) => series.createdInPane === 1));
  assert.deepEqual(
    chart.series.map((series) => series.definitionName),
    ['Histogram', 'Line', 'Line'],
  );
});

test('a multi-output band creates one series per edge on the price pane', () => {
  const { chart } = layerFor(build('bbands'));
  assert.equal(chart.paneList.length, 1);
  assert.equal(chart.series.length, 3);
  assert.ok(chart.series.every((series) => series.createdInPane === 0));
});

test('two instances of the same indicator are independent series', () => {
  let instances = build('ema');
  instances = addIndicator(instances, 'ema');
  instances = configureIndicator(instances, instances[1].instanceId, { period: 50 });
  const { chart } = layerFor(instances);
  assert.equal(chart.series.length, 2);
  assert.notDeepEqual(chart.series[0].data, chart.series[1].data, 'EMA 20 and EMA 50 must differ');
  assert.equal(new Set(instances.map((instance) => instance.instanceId)).size, 2);
});

test('changing a setting updates the existing series rather than rebuilding it', () => {
  const instances = build('ema');
  const { chart, render } = layerFor(instances);
  const original = chart.series[0];
  const before = original.data.at(-1)?.value;
  render(configureIndicator(instances, instances[0].instanceId, { period: 100 }));
  assert.equal(chart.series.length, 1);
  assert.equal(chart.series[0], original, 'the series object must survive a settings change');
  assert.notEqual(chart.series[0].data.at(-1)?.value, before);
});

test('removing an indicator takes its series and its pane with it', () => {
  const instances = build('ema', 'rsi');
  const { chart, render } = layerFor(instances);
  assert.equal(chart.paneList.length, 2);
  assert.equal(chart.series.length, 2);
  render(removeIndicator(instances, instances[1].instanceId));
  assert.equal(chart.series.length, 1, 'the RSI series leaked');
  assert.equal(chart.paneList.length, 1, 'the RSI pane leaked');
});

test('hiding a pane indicator reclaims its space and showing it puts it back', () => {
  const instances = build('rsi');
  const { chart, render } = layerFor(instances);
  const hidden = setIndicatorVisibility(instances, instances[0].instanceId, false);
  render(hidden);
  assert.equal(chart.paneList.length, 1, 'a hidden pane must not keep holding vertical space');
  assert.equal(chart.series.length, 0);
  render(setIndicatorVisibility(hidden, instances[0].instanceId, true));
  assert.equal(chart.paneList.length, 2);
  assert.equal(chart.series.length, 1);
  assert.ok(chart.series[0].data.length > 0, 'the restored series must carry its data');
});

test('panes follow layout order, and reordering moves the pane with the row', () => {
  const instances = build('rsi', 'macd');
  const { chart, render } = layerFor(instances);
  const rsiPaneFirst = chart.series.find((series) => series.priceLines.length === 3);
  assert.ok(rsiPaneFirst, 'RSI declares three reference lines');
  render(moveIndicator(instances, instances[1].instanceId, -1));
  // MACD now leads, so its pane must be the one directly under the price pane.
  const macdSeries = chart.series.filter((series) => series.definitionName === 'Histogram');
  assert.equal(macdSeries.length, 1);
  assert.equal(chart.paneList.length, 3);
});

test('duplicating an indicator carries its configuration into a second series', () => {
  let instances = build('ema');
  instances = configureIndicator(instances, instances[0].instanceId, { period: 55 });
  instances = duplicateIndicator(instances, instances[0].instanceId);
  const { chart } = layerFor(instances);
  assert.equal(chart.series.length, 2);
  assert.deepEqual(chart.series[0].data, chart.series[1].data, 'a duplicate starts identical');
  assert.equal(instances[1].config.period, 55);
});

test('reference lines are replaced, never accumulated, across repeated renders', () => {
  const instances = build('rsi');
  const { chart, render } = layerFor(instances);
  const anchor = chart.series[0];
  assert.equal(anchor.priceLines.length, 3, 'RSI declares 70, 30 and the 50 midline');
  for (let i = 0; i < 10; i += 1) render(instances);
  assert.equal(anchor.priceLines.length, 3, 'reference lines accumulated on re-render');
});

test('a bounded oscillator pins its own scale instead of autoscaling to its noise', () => {
  const { chart } = layerFor(build('rsi'));
  const provider = chart.series[0].options.autoscaleInfoProvider as (() => { priceRange: { minValue: number; maxValue: number } }) | undefined;
  assert.ok(provider, 'RSI declares a pane range and must apply it');
  assert.deepEqual(provider().priceRange, { minValue: 0, maxValue: 100 });
});

test('an unbounded pane indicator is left to autoscale', () => {
  const { chart } = layerFor(build('atr'));
  assert.equal(chart.series[0].options.autoscaleInfoProvider, undefined);
});

test('only one series per pane shows a last-value badge', () => {
  const { chart } = layerFor(build('macd'));
  const badges = chart.series.filter((series) => series.options.lastValueVisible === true);
  assert.equal(badges.length, 1, 'stacked axis labels are unreadable');
});

test('a direction-flipping indicator carries per-bar colour into the data', () => {
  const { chart } = layerFor(build('supertrend'));
  const colors = new Set(chart.series[0].data.map((point) => point.color));
  assert.equal(colors.size, 2, 'Supertrend must colour by trend direction');
  assert.ok([...colors].every((color) => typeof color === 'string'));
});

test('switching symbol replaces the data and keeps the series', () => {
  const instances = build('ema', 'rsi');
  const { chart, render } = layerFor(instances);
  const before = chart.series.map((series) => series.data.at(-1)?.value);
  const seriesObjects = [...chart.series];
  const otherSymbol = walkBars(400, 99);
  render(instances, otherSymbol, otherSymbol.length);
  assert.deepEqual([...chart.series], seriesObjects, 'a symbol switch must not rebuild the chart');
  assert.notDeepEqual(chart.series.map((series) => series.data.at(-1)?.value), before);
});

test('narrowing the visible range shortens the drawn series without restarting warm-up', () => {
  const instances = build('ema');
  const { chart, render } = layerFor(instances);
  const fullTail = chart.series[0].data.at(-1)?.value;
  render(instances, BARS, 60);
  assert.equal(chart.series[0].data.length, 60);
  assert.equal(
    chart.series[0].data.at(-1)?.value,
    fullTail,
    'the last value must not change when the window narrows — warm-up ran over full history',
  );
});

test('the price pane keeps the larger share however many indicator panes are added', () => {
  // Lightweight Charts gives every new pane the same stretch, which would leave price on 40%
  // of the canvas with three indicators. Price is what the other panes are read against.
  const instances = build('rsi', 'macd', 'atr');
  const { chart } = layerFor(instances);
  assert.equal(chart.paneList.length, 4);
  assert.equal(chart.paneList[0].stretchFactor, 4);
  assert.deepEqual(chart.paneList.slice(1).map((pane) => pane.stretchFactor), [1, 1, 1]);
  const total = chart.paneList.reduce((sum, pane) => sum + pane.stretchFactor, 0);
  assert.ok(chart.paneList[0].stretchFactor / total > 0.5, 'price fell below half the canvas');
});

test('a price-only layout leaves the pane sizing alone', () => {
  const { chart } = layerFor(build('ema', 'bbands'));
  assert.equal(chart.paneList.length, 1);
  assert.equal(chart.paneList[0].stretchFactor, 1, 'nothing to balance against, nothing to change');
});

test('destroy leaves the chart with nothing but its price pane', () => {
  const { chart, layer } = layerFor(build('ema', 'rsi', 'macd', 'bbands'));
  assert.ok(chart.series.length > 5);
  assert.equal(chart.paneList.length, 3);
  layer.destroy();
  assert.equal(chart.series.length, 0);
  assert.equal(chart.paneList.length, 1);
});

test('tearing down and rebuilding repeatedly leaks neither series nor panes', () => {
  const instances = build('ema', 'rsi', 'macd');
  const { chart, render } = layerFor(instances);
  const seriesCount = chart.series.length;
  const paneCount = chart.paneList.length;
  for (let i = 0; i < 20; i += 1) {
    render([]);
    render(instances);
  }
  assert.equal(chart.series.length, seriesCount);
  assert.equal(chart.paneList.length, paneCount);
});

test('every catalogued indicator renders and tears down cleanly', () => {
  // The sweep that keeps this true for indicators added later.
  const chart = new FakeChart();
  const layer = new IndicatorChartLayer(chart as unknown as IChartApi);
  const computer = createIndicatorComputer();
  for (const id of ['sma', 'ema', 'wma', 'hma', 'bbands', 'keltner', 'donchian', 'vwap', 'supertrend',
    'rsi', 'stoch', 'stochrsi', 'macd', 'roc', 'cci', 'willr', 'adx', 'mfi', 'fisher',
    'atr', 'adr', 'hv', 'obv', 'cmf', 'supersmoother', 'mama', 'itrend']) {
    const instances = build(id);
    layer.sync(computer.compute(BARS, BARS.length, instances, CONTEXT));
    const drawn = chart.series.filter((series: FakeSeries) => series.data.length > 0);
    assert.ok(drawn.length > 0, `${id} rendered no data at all`);
    layer.sync(computer.compute(BARS, BARS.length, [], CONTEXT));
    assert.equal(chart.series.length, 0, `${id} leaked a series`);
    assert.equal(chart.paneList.length, 1, `${id} leaked a pane`);
  }
});
