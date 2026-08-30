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
  const render = (next: IndicatorInstance[], nextBars = bars, nextVisible = visible, priceStretch = 4) =>
    layer.sync(computer.compute(nextBars, nextVisible, next, CONTEXT), priceStretch);
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

test('pane elements are exposed for anchoring, one per pane indicator, in layout order', () => {
  const instances = build('ema', 'rsi', 'macd');
  const { chart, layer } = layerFor(instances);
  const anchored = layer.paneElements();
  // The price overlay contributes nothing: it has no pane to anchor to.
  assert.deepEqual(anchored.map((entry) => entry.instanceId), ['rsi#1', 'macd#1']);
  assert.ok(anchored.every((entry) => entry.element));
  assert.equal(new Set(anchored.map((entry) => entry.element)).size, 2, 'each pane is a distinct element');
  assert.equal(chart.paneList.length, 3);
});

test('a pane that has not been laid out yet is skipped rather than anchored to null', () => {
  // getHTMLElement() is documented to return null before layout. A control positioned
  // against that would land at the top-left of the chart rather than on its pane.
  const { chart, layer } = layerFor(build('rsi', 'atr'));
  chart.paneList[1].element = null;
  const anchored = layer.paneElements();
  assert.equal(anchored.length, 1);
  assert.equal(anchored[0].instanceId, 'atr#1');
});

test('removing an indicator stops exposing its pane element', () => {
  const instances = build('rsi', 'macd');
  const { layer, render } = layerFor(instances);
  assert.equal(layer.paneElements().length, 2);
  render(removeIndicator(instances, 'rsi#1'));
  assert.deepEqual(layer.paneElements().map((entry) => entry.instanceId), ['macd#1']);
  render([]);
  assert.deepEqual(layer.paneElements(), []);
});

test('a hidden pane indicator exposes no element to anchor to', () => {
  const instances = build('rsi');
  const { layer, render } = layerFor(instances);
  assert.equal(layer.paneElements().length, 1);
  render(setIndicatorVisibility(instances, 'rsi#1', false));
  assert.deepEqual(layer.paneElements(), [], 'a hidden indicator has no pane at all');
});

test('removing the FIRST of several pane indicators does not take a sibling with it', () => {
  // removePane takes an INDEX, so this is the case that would go wrong if a pane ever
  // self-collected before the explicit removal: the captured index would then address the
  // NEXT pane and delete a different indicator's. Confirmed in a real browser too.
  const instances = build('rsi', 'macd', 'atr');
  const { chart, render } = layerFor(instances);
  assert.equal(chart.paneList.length, 4);
  render(removeIndicator(instances, 'rsi#1'));
  assert.equal(chart.paneList.length, 3, 'exactly one pane should have gone');
  const survivors = chart.series.filter((series) => series.data.length > 0);
  assert.ok(survivors.some((series) => series.definitionName === 'Histogram'), 'MACD lost its histogram');
  assert.equal(chart.series.filter((series) => series.options.color).length, chart.series.length);
});

test('an emptied pane is removed rather than left holding vertical space', () => {
  // Panes are created preserved so the gap before their first series cannot drop them, which
  // means nothing collects them on the way out either — the explicit removal is load-bearing.
  const instances = build('macd');
  const { chart, render } = layerFor(instances);
  assert.equal(chart.paneList.length, 2);
  assert.equal(chart.paneList[1].preserve, true, 'created preserved');
  render([]);
  assert.equal(chart.paneList.length, 1, 'an empty pane survived its indicator');
  assert.equal(chart.series.length, 0);
});

/** Run an indicator's autoscale provider against a data range, the way the chart does. */
function autoscale(chart: FakeChart, seriesIndex: number, min: number, max: number) {
  const provider = chart.series[seriesIndex].options.autoscaleInfoProvider as
    ((original: () => unknown) => { priceRange: { minValue: number; maxValue: number } } | null) | undefined;
  assert.ok(provider, 'expected an autoscale provider on this series');
  return provider(() => ({ priceRange: { minValue: min, maxValue: max } }));
}

test('an oscillator scales to its DATA, not to its theoretical range', () => {
  // RSI lives between roughly 30 and 70. Pinning the pane to a flat 0-100 leaves a third of
  // an already-short pane permanently empty and the line reading as flat — the peaks and
  // troughs are the entire point of the indicator.
  const { chart } = layerFor(build('rsi'));
  const fitted = autoscale(chart, 0, 38, 64);
  assert.deepEqual(fitted?.priceRange, { minValue: 30, maxValue: 70 }, 'fits the data, widened only to keep the bands');
});

test('reference bands stay on screen through a quiet stretch', () => {
  // Without folding the levels in, an RSI sitting at 45-55 would scale its own 70/30 bands
  // off the pane — removing the thing the reading is judged against.
  const { chart } = layerFor(build('rsi'));
  assert.deepEqual(autoscale(chart, 0, 47, 53)?.priceRange, { minValue: 30, maxValue: 70 });
  // MACD has no bounded range, but its zero line is the signal and must stay visible.
  const macd = layerFor(build('macd')).chart;
  const histogramIndex = macd.series.findIndex((series) => series.options.autoscaleInfoProvider);
  const provider = macd.series[histogramIndex].options.autoscaleInfoProvider as (o: () => unknown) => { priceRange: { minValue: number; maxValue: number } };
  assert.deepEqual(provider(() => ({ priceRange: { minValue: 2, maxValue: 9 } })).priceRange, { minValue: 0, maxValue: 9 });
});

test('a declared range is a ceiling, never a floor', () => {
  // It stops padding implying an RSI above 100; it must not force the view wider than the
  // data, which is what made the pane look flat.
  const { chart } = layerFor(build('rsi'));
  assert.deepEqual(autoscale(chart, 0, -20, 140)?.priceRange, { minValue: 0, maxValue: 100 }, 'clamped to the declared bounds');
  const willr = layerFor(build('willr')).chart;
  const provider = willr.series[0].options.autoscaleInfoProvider as (o: () => unknown) => { priceRange: { minValue: number; maxValue: number } };
  assert.deepEqual(provider(() => ({ priceRange: { minValue: -95, maxValue: -5 } })).priceRange, { minValue: -95, maxValue: -5 });
});

test('an indicator with neither bounds nor bands is left to plain autoscale', () => {
  // ATR, OBV and friends: nothing to fold in, so nothing to override. Double-click reset on
  // their axis behaves exactly as it does on the price pane.
  const { chart } = layerFor(build('atr'));
  assert.equal(chart.series[0].options.autoscaleInfoProvider, undefined);
});

test('indicator panes take symmetric margins', () => {
  // The library default reserves 20% above and 10% below — right for price, where the
  // last-value badge and recent action sit at the top, lopsided for an oscillator read
  // against its own midline.
  const { chart } = layerFor(build('rsi'));
  assert.deepEqual(chart.priceScale('right', 1).scaleMargins, { top: 0.1, bottom: 0.1 });
});

test('nothing forces autoScale back on, so a pane axis drags and resets like any other', () => {
  const { chart, render } = layerFor(build('rsi'));
  const scale = chart.priceScale('right', 1);
  scale.autoScale = false; // an axis drag
  render(build('rsi'));
  assert.equal(scale.autoScale, false, 'a manual scale on an indicator pane is the operator\'s to keep');
});

test('a stored pane division is applied instead of the default weighting', () => {
  let instances = build('rsi', 'macd');
  instances = instances.map((instance) => (instance.instanceId === 'rsi#1' ? { ...instance, paneStretch: 2.5 } : instance));
  const { chart } = layerFor(instances);
  const [price, rsi, macd] = chart.paneList;
  assert.equal(rsi.stretchFactor, 2.5, 'the dragged height');
  assert.equal(macd.stretchFactor, 1, 'the default, for a pane never dragged');
  assert.equal(price.stretchFactor, 4);
});

test('the price pane honours a stored division too', () => {
  const { chart } = layerFor(build('rsi'), BARS, BARS.length);
  assert.equal(chart.paneList[0].stretchFactor, 4);
  const chart2 = new FakeChart();
  const layer2 = new IndicatorChartLayer(chart2 as unknown as IChartApi);
  layer2.sync(createIndicatorComputer().compute(BARS, BARS.length, build('rsi'), CONTEXT), 2.2);
  assert.equal(chart2.paneList[0].stretchFactor, 2.2);
});

test('pane divisions are read back for persistence, price pane included', () => {
  const instances = build('rsi', 'macd');
  const { chart, layer } = layerFor(instances);
  chart.paneList[0].stretchFactor = 3.3;
  chart.paneList[1].stretchFactor = 1.2;
  chart.paneList[2].stretchFactor = 1.5;
  const read = layer.readPaneStretch();
  assert.equal(read.priceStretch, 3.3);
  assert.deepEqual(read.byInstance, { 'rsi#1': 1.2, 'macd#1': 1.5 });
  assert.equal(Object.keys(read.byInstance).length, 2, 'price overlays own no pane and are not reported');
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
