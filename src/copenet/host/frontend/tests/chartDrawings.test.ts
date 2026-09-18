import assert from 'node:assert/strict';
import test from 'node:test';
import type { IChartApi, ISeriesApi, SeriesAttachedParameter } from 'lightweight-charts';
import type { ChartObject } from '../src/sections/market/chartAgent/types';
import { anchorIndexAt, hitDrawing, projectDrawing, replaceAnchor } from '../src/sections/market/drawings/geometry';
import { DrawingPrimitive } from '../src/sections/market/drawings/primitive';
import { readChartViewport } from '../src/sections/market/drawings/useChartWorkspace';
import { futureDrawingTimes } from '../src/sections/market/chartDecorations';
import { beginTouch, dragTouch, touchCommits } from '../src/sections/market/drawings/touchPlacement';
import { DRAWING_KINDS, strokeOf } from '../src/sections/market/drawings/kinds';
import type { ChartRenderReceipt, ChartWorkspaceBridge } from '../src/sections/market/drawings/types';

function object(kind: ChartObject['kind'] = 'level'): ChartObject {
  const anchors = kind === 'position' || kind === 'channel' ? [{ t: 100, value: 10 }, { t: 400, value: 100 }, { t: 400, value: 80 }]
    : kind === 'zone' || kind === 'trendline' || kind === 'extended_trendline' || kind === 'ray' || kind === 'measurement' || kind === 'fib_retracement' ? [{ t: 100, value: 10 }, { t: 400, value: 100 }]
      : [{ t: 100, value: 10 }];
  return { id: kind, kind, anchors,
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

test('composite drawing tools project their derived geometry', () => {
  for (const kind of ['extended_trendline', 'ray', 'measurement', 'fib_retracement', 'channel', 'position'] as ChartObject['kind'][]) {
    const geometry = projectDrawing(object(kind), projection);
    assert.ok(geometry, `${kind} should project`);
    assert.ok(geometry.lines?.length || geometry.regions?.length || geometry.annotations?.length, `${kind} should render more than handles`);
  }
});

test('unknown time anchors and nonfinite transforms cannot create invented drawing positions', () => {
  const drawing = object();
  drawing.anchors[0].t = 200;
  assert.equal(projectDrawing(drawing, projection), null);
  assert.equal(projectDrawing(object(), { ...projection, price: () => Number.NaN }), null);
});

test('drawing timeline reserves future candle slots without changing real bars', () => {
  assert.deepEqual(futureDrawingTimes([{ t: 100, o: 1, h: 2, l: 1, c: 2, v: 3 }, { t: 200, o: 2, h: 3, l: 2, c: 3, v: 4 }], 3), [300, 400, 500]);
});

function bridge(objects: ChartObject[], receipts: ChartRenderReceipt[]): ChartWorkspaceBridge {
  return { documentId: 'document', revision: 1, objects, timeframe: 'D', enabled: true,
    selectedObjectId: null, mode: 'select', onViewport() {}, onSelectRange() {}, onSelectObject() {}, onDeleteObject() {}, onCreate() {}, onUpdate() {},
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

test('touch placement drops a cursor on the first tap, moves it by the drag delta from anywhere, and commits on a plain tap', () => {
  const pane = { width: 400, height: 300 };
  const first = beginTouch(null, { x: 100, y: 100 });
  assert.equal(dragTouch(first, { x: 102, y: 101 }, pane), null);
  assert.equal(touchCommits(first), false, 'the first tap only positions the cursor');

  const drag = beginTouch({ x: 100, y: 100 }, { x: 300, y: 250 });
  assert.deepEqual(dragTouch(drag, { x: 330, y: 230 }, pane), { x: 130, y: 80 });
  assert.deepEqual(dragTouch(drag, { x: 900, y: -500 }, pane), { x: 400, y: 0 }, 'the cursor stays inside the price pane');
  assert.equal(touchCommits(drag), false, 'a drag never commits');

  assert.equal(touchCommits(beginTouch({ x: 130, y: 80 }, { x: 10, y: 10 })), true);
});

test('each drawing form inherits the settings of the form before it, and anchor counts match the backend contract', () => {
  // Mirrors ChartObject.anchor_count in chart_workspace/models.py.
  const backend = { level: 1, zone: 2, trendline: 2, extended_trendline: 2, label: 1, horizontal_ray: 1, ray: 2, vertical_line: 1,
    measurement: 2, position: 3, channel: 3, avwap: 1, fib_retracement: 2, callout: 1 };
  assert.deepEqual(Object.fromEntries(Object.entries(DRAWING_KINDS).map(([kind, spec]) => [kind, spec.anchors]).sort()), Object.fromEntries(Object.entries(backend).sort()));
  for (const spec of Object.values(DRAWING_KINDS)) {
    if (spec.form === 'point') assert.equal(spec.stroke || spec.fill, false, 'a point has nothing to stroke');
    else assert.equal(spec.stroke, true, `${spec.label} is built on a line and keeps its stroke`);
    if (spec.form === 'area') assert.equal(spec.fill, true);
  }
});

test('a drawing with no saved style renders the owner default, and a saved style wins', () => {
  const base = { id: 'x', kind: 'trendline', anchors: [], timeframe: 'D', label: '', color: '#ffffff', visible: true, rationale: '', evidence: [] } as const;
  assert.deepEqual(strokeOf({ ...base, anchors: [], evidence: [], owner: { kind: 'agent' } }), { width: 1, style: 'dashed' });
  assert.deepEqual(strokeOf({ ...base, anchors: [], evidence: [], owner: { kind: 'operator' } }), { width: 1, style: 'solid' });
  assert.deepEqual(strokeOf({ ...base, anchors: [], evidence: [], owner: { kind: 'agent' }, lineStyle: 'solid', lineWidth: 3 }), { width: 3, style: 'solid' });
});

test('a measurement is a signed box: green when price rose, red when it fell, with its size written inside', () => {
  const up = projectDrawing(object('measurement'), { ...projection, barsBetween: () => 7 })!;
  assert.equal(up.lines, undefined, 'no ray from start to stop');
  assert.equal(up.regions![0].color, '#69c589');
  assert.match(up.annotations![0].text, /^\+90\.00 \(\+900\.0%\) · 7 bars · /);
  const fell = { ...object('measurement'), anchors: [{ t: 100, value: 100 }, { t: 400, value: 10 }] };
  assert.equal(projectDrawing(fell, projection)!.regions![0].color, '#d96d5f');
  assert.equal(hitDrawing(up, { x: 30, y: (up.regions![0].top + up.regions![0].height / 2) }), true, 'the whole box selects it');
});

test('drawings can reach far past the latest candle', () => {
  const rows = [{ t: 100, o: 1, h: 1, l: 1, c: 1, v: 1 }, { t: 200, o: 1, h: 1, l: 1, c: 1, v: 1 }];
  const times = futureDrawingTimes(rows);
  assert.ok(times.length >= 200, 'roughly a trading year of room on a daily chart');
  assert.equal(times[0], 300);
});

test('the settings popup saves one patch holding only what changed', async () => {
  const { drawingPatch } = await import('../src/sections/market/drawings/patch');
  const original = object('trendline');
  const draft = { ...original, kind: 'ray' as const, lineWidth: 3, timeframes: ['D', 'W'] as ChartObject['timeframe'][] };
  assert.deepEqual(drawingPatch(original, draft), { kind: 'ray', lineWidth: 3, timeframes: ['D', 'W'] });
  assert.deepEqual(drawingPatch(original, { ...original }), {});
});

test('a drawing shown on another timeframe lands on the candle that contains its anchor', async () => {
  const { snapToBar } = await import('../src/sections/market/drawings/reads');
  const { shownOn } = await import('../src/sections/market/drawings/kinds');
  const weekly = [100, 800, 1500].map((t) => ({ t, o: 1, h: 1, l: 1, c: 1, v: 1 }));
  assert.equal(snapToBar(weekly, 900), 800);
  assert.equal(snapToBar(weekly, 50), null, 'before the loaded range there is no candle to land on');
  assert.equal(shownOn(object('level'), 'W'), false);
  assert.equal(shownOn({ ...object('level'), timeframes: ['D', 'W'] }, 'W'), true);
});

test('stats painted beside a line are the numbers the model reads for it', () => {
  const geometry = projectDrawing({ ...object('ray'), showStats: true }, { ...projection, barsBetween: () => 10 })!;
  assert.equal(geometry.annotations![0].text, '+90.00 (+900.0%) · 10 bars · +9.00/bar');
});
