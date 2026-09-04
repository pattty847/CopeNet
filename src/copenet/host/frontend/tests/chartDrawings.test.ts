import assert from 'node:assert/strict';
import test from 'node:test';
import type { IChartApi, ISeriesApi, SeriesAttachedParameter } from 'lightweight-charts';
import type { ChartObject } from '../src/sections/market/chartAgent/types';
import { anchorIndexAt, hitDrawing, projectDrawing, replaceAnchor } from '../src/sections/market/drawings/geometry';
import { DrawingPrimitive } from '../src/sections/market/drawings/primitive';
import { readChartViewport } from '../src/sections/market/drawings/useChartWorkspace';
import type { ChartRenderReceipt, ChartWorkspaceBridge } from '../src/sections/market/drawings/types';

function object(kind: ChartObject['kind'] = 'level'): ChartObject {
  return { id: kind, kind, anchors: kind === 'zone' || kind === 'trendline' ? [{ t: 100, value: 10 }, { t: 400, value: 100 }] : [{ t: 100, value: 10 }],
    timeframe: 'D', label: 'Evidence', color: '#fb9423', visible: true, rationale: '', evidence: [], owner: { kind: 'operator' } };
}

const projection = {
  // Two far-apart timestamps still occupy adjacent candle slots.
  time: (time: number) => new Map([[100, 20], [400, 40]]).get(time) ?? null,
  price: (price: number) => 100 - Math.log10(price) * 30,
  width: 200, height: 100,
};

test('drawing anchors use candle slots and the current logarithmic price transform without changing source anchors', () => {
  const source = object('trendline');
  const geometry = projectDrawing(source, projection)!;
  assert.deepEqual(geometry.points, [{ x: 20, y: 70 }, { x: 40, y: 40 }]);
  assert.deepEqual(source.anchors, [{ t: 100, value: 10 }, { t: 400, value: 100 }]);
  assert.equal(hitDrawing(geometry, { x: 30, y: 55 }), true);
  assert.equal(hitDrawing(geometry, { x: 130, y: 55 }), false);
  assert.equal(anchorIndexAt(geometry, { x: 40, y: 42 }), 1);
  assert.deepEqual(replaceAnchor(source.anchors, 1, { t: 400, value: 90 }), [{ t: 100, value: 10 }, { t: 400, value: 90 }]);
  assert.equal(source.anchors[1].value, 100);
});

test('levels span only the price pane and zones accept reversed anchors', () => {
  assert.equal(hitDrawing(projectDrawing(object(), projection)!, { x: 195, y: 71 }), true);
  assert.equal(hitDrawing(projectDrawing(object(), projection)!, { x: 195, y: 130 }), false);
  const zone = object('zone');
  zone.anchors.reverse();
  assert.equal(hitDrawing(projectDrawing(zone, projection)!, { x: 30, y: 50 }), true);
  assert.equal(hitDrawing(projectDrawing(zone, projection)!, { x: 60, y: 50 }), false);
  assert.equal(hitDrawing(projectDrawing(object('label'), projection)!, { x: 25, y: 68 }), true);
});

test('unknown time anchors and nonfinite transforms cannot create invented drawing positions', () => {
  const drawing = object();
  drawing.anchors[0].t = 200;
  assert.equal(projectDrawing(drawing, projection), null);
  assert.equal(projectDrawing(object(), { ...projection, price: () => Number.NaN }), null);
});

function bridge(objects: ChartObject[], receipts: ChartRenderReceipt[]): ChartWorkspaceBridge {
  return { documentId: 'document', revision: 1, objects, timeframe: 'D', enabled: true,
    selectedObjectId: null, mode: 'select', onViewport() {}, onSelectRange() {}, onSelectObject() {}, onCreate() {}, onUpdate() {},
    onRendered: (receipt) => receipts.push(receipt) };
}

function attach(primitive: DrawingPrimitive): void {
  primitive.attached({
    chart: { paneSize: () => ({ width: 200, height: 100 }), timeScale: () => ({ timeToCoordinate: projection.time }) },
    series: { priceToCoordinate: projection.price }, requestUpdate() {},
  } as unknown as SeriesAttachedParameter);
}

function paint(primitive: DrawingPrimitive): string[] {
  const operations: string[] = [];
  const context = new Proxy({}, {
    get: (_target, property) => (...values: unknown[]) => { operations.push(`${String(property)}:${values.join(',')}`); },
    set: () => true,
  });
  const renderer = primitive.paneViews()[0].renderer()!;
  renderer.draw({
    useMediaCoordinateSpace: (callback: (scope: unknown) => void) => callback({ context, mediaSize: { width: 200, height: 100 } }),
  } as unknown as Parameters<typeof renderer.draw>[0]);
  return operations;
}

test('primitive paints inside its own pane, emits a receipt only after paint, and hides incompatible intervals', async () => {
  const oldDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { visibilityState: 'visible' } });
  try {
    const primitive = new DrawingPrimitive();
    const receipts: ChartRenderReceipt[] = [];
    const state = bridge([object('level'), object('zone'), object('trendline'), object('label')], receipts);
    attach(primitive);
    primitive.setState(state, false);
    assert.equal(receipts.length, 0);
    const operations = paint(primitive);
    await Promise.resolve();
    assert.deepEqual(receipts[0].objectIds, ['level', 'zone', 'trendline', 'label']);
    assert.equal(receipts[0].status, 'rendered');
    assert.ok(operations.includes('rect:0,0,200,100'), 'pane clipping must use CSS media coordinates, independently of DPR');
    assert.ok(operations.includes('moveTo:20,70'), 'primitive x coordinates must not include the left axis width');
    paint(primitive);
    await Promise.resolve();
    assert.equal(receipts.length, 1, 'pan/zoom repaint must not spam revision receipts');
    primitive.setState({ ...state, timeframe: 'W' }, false);
    paint(primitive);
    await Promise.resolve();
    assert.equal(receipts[1].status, 'hidden');
    assert.equal(primitive.hitTest(30, 55), null);
    primitive.setState({ ...state, revision: 2 }, true);
    await Promise.resolve();
    assert.equal(receipts[2].status, 'hidden', 'comparison hides the candle series so cannot wait for its primitive paint');
    primitive.detached();
  } finally {
    if (oldDocument) Object.defineProperty(globalThis, 'document', oldDocument);
    else Reflect.deleteProperty(globalThis, 'document');
  }
});

test('navigation before queued receipt cannot acknowledge the previous document as rendered', async () => {
  const primitive = new DrawingPrimitive();
  const receipts: ChartRenderReceipt[] = [];
  attach(primitive);
  primitive.setState(bridge([object()], receipts), true);
  primitive.setState({ ...bridge([object()], receipts), documentId: 'other' }, true);
  await Promise.resolve();
  assert.deepEqual(receipts.map((receipt) => receipt.documentId), ['other']);
});

test('a hidden chart container cannot acknowledge paint even in a foreground browser tab', async () => {
  const oldDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { visibilityState: 'visible' } });
  try {
    let visible = false;
    const primitive = new DrawingPrimitive(() => visible);
    const receipts: ChartRenderReceipt[] = [];
    attach(primitive);
    primitive.setState(bridge([object()], receipts), false);
    paint(primitive);
    await Promise.resolve();
    assert.equal(receipts.length, 0);
    visible = true;
    paint(primitive);
    await Promise.resolve();
    assert.equal(receipts[0].status, 'rendered');
  } finally {
    if (oldDocument) Object.defineProperty(globalThis, 'document', oldDocument);
    else Reflect.deleteProperty(globalThis, 'document');
  }
});

test('viewport includes partially visible candles and retains logical whitespace boundaries', () => {
  const calls: number[] = [];
  const chart = { timeScale: () => ({ getVisibleLogicalRange: () => ({ from: 0.3, to: 1.6 }) }) } as unknown as IChartApi;
  const candle = { dataByIndex: (index: number) => { calls.push(index); return { time: [100, 400, 800][index], close: 10 }; } } as unknown as ISeriesApi<'Candlestick'>;
  assert.deepEqual(readChartViewport(chart, candle), { from: 100, to: 800, logicalFrom: 0.3, logicalTo: 1.6 });
  assert.deepEqual(calls, [0, 2]);
});

test('future marker whitespace cannot become a captured candle range', () => {
  const rows = [{ time: 100, close: 10 }, { time: 400, close: 12 }, { time: 800 }];
  let range = { from: 0, to: 4 };
  const chart = { timeScale: () => ({ getVisibleLogicalRange: () => range }) } as unknown as IChartApi;
  const candle = { dataByIndex: (index: number) => rows[Math.min(2, index)], data: () => rows } as unknown as ISeriesApi<'Candlestick'>;
  assert.deepEqual(readChartViewport(chart, candle), { from: 100, to: 400, logicalFrom: 0, logicalTo: 4 });
  range = { from: 2, to: 4 };
  assert.deepEqual(readChartViewport(chart, candle), { from: null, to: null, logicalFrom: 2, logicalTo: 4 });
});
