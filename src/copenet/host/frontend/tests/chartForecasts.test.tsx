import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import type { SeriesAttachedParameter } from 'lightweight-charts';
import { ForecastPrimitive } from '../src/sections/market/forecasts/primitive';
import { forecastDisplay, forecastLevels, forecastRisk, forecastStatus, forecastTracking, forecastThesis } from '../src/sections/market/forecasts/model';
import { ForecastList } from '../src/sections/market/forecasts/ForecastList';
import { createMarketForecastApi } from '../src/lib/wsMarketForecasts';
import type { ForecastBridge, ForecastRecord, ForecastRenderReceipt } from '../src/sections/market/forecasts/types';

function forecast(): ForecastRecord {
  return { forecastId: 'forecast', requestId: 'forecast', documentId: 'document', observationId: 'observation', sessionKey: 'chart',
    instrument: { instrumentId: 'yahoo:TEST', symbol: 'TEST', assetClass: 'equity', source: 'yahoo', currency: 'USD' },
    provider: 'test', model: 'test-model', paired: true, detail: 'balanced', entryExpirySessions: 10, trackingScanId: null,
    status: 'published', revision: 1, requestedAt: '2026-01-02T22:00:00Z', capturedAt: 1767391200, publishedAt: '2026-01-02T22:00:00Z',
    deadlineAt: '2026-02-27T22:00:00Z', provenance: { splitFingerprint: 'original' },
    members: { ta: { sessionKey: 'ta', observationId: 'ta-observation', runId: 'run', status: 'submitted', errors: [], attribution: {},
      result: { kind: 'setup', direction: 'long', thesis: 'Synthetic setup', entry: { kind: 'limit', price: 100 }, stop: 90,
        targets: [{ price: 120, fraction: 1 }], zones: [], evidence: [{ observationId: 'ta-observation', resourceKey: 'candles:D' }] } } },
    evaluation: { state: 'stopped', health: 'ready', plannedRiskR: -1,
      horizons: { '8w': { dueAt: '', endpointDate: '', endpointCloseAt: '', referenceClose: 100, endpointClose: 120, priceReturn: 0.2, status: 'resolved', members: { ta: { direction: 'bullish', outcome: 'correct' } } } } },
    events: [], amendments: [], renderStatus: [] };
}

test('forecast rows distinguish a stopped trade from a correct direction and paused tracking', () => {
  const record = forecast();
  const html = renderToStaticMarkup(<ForecastList records={[record]} onSelect={() => undefined} />);
  assert.match(html, /stopped/); assert.match(html, /-1.00R/); assert.match(html, /8w correct/);
  assert.match(html, /Tracking paused/); assert.equal(forecastTracking(record), 'paused');
  record.evaluation = { state: 'ambiguous', health: 'ready', plannedRiskR: null };
  assert.equal(forecastRisk(record), '—');
  assert.match(renderToStaticMarkup(<ForecastList records={[record]} onSelect={() => undefined} />), /ambiguous/);
  record.status = 'generating'; record.evaluation = null;
  assert.doesNotThrow(() => renderToStaticMarkup(<ForecastList records={[record]} onSelect={() => undefined} />));
  assert.equal(forecastStatus(record), 'generating'); assert.equal(forecastRisk(record), '—');
});

test('split display rescales only confirmed prices and never changes the frozen original', () => {
  const record = forecast(); const original = structuredClone(record.members.ta!.result);
  assert.ok(forecastDisplay(record, 'unknown').reason);
  record.provenance = { splitFingerprint: '' };
  assert.equal(forecastDisplay(record, '').reason, undefined, 'An empty no-splits fingerprint is a valid price basis');
  record.evaluation!.source = { splitFingerprint: 'split', publicationBasisFactor: 2 };
  const display = forecastDisplay(record, 'split');
  assert.equal(display.reason, undefined);
  assert.deepEqual(forecastLevels(record, display.factor).map((level) => level.price), [50, 45, 60]);
  assert.deepEqual(record.members.ta!.result, original);
  record.evaluation!.health = 'revision_review'; assert.ok(forecastDisplay(record, 'split').reason);
});

test('forecast primitive is independently clipped, selectable and hidden honestly without drawing mutation', async () => {
  const oldDocument = Object.getOwnPropertyDescriptor(globalThis, 'document');
  Object.defineProperty(globalThis, 'document', { configurable: true, value: { visibilityState: 'visible' } });
  try {
    const record = forecast(); const original = structuredClone(record);
    const receipts: ForecastRenderReceipt[] = [];
    const bridge: ForecastBridge = { records: [record], hidden: new Set(), splitFingerprint: 'original', viewId: 'view', onSelect() {}, onRendered: (receipt) => { receipts.push(receipt); } };
    const primitive = new ForecastPrimitive(() => true);
    const calls: string[] = [];
    const context = new Proxy({}, { get: (_target, property) => (...values: unknown[]) => calls.push(`${String(property)}:${values.join(',')}`), set: () => true });
    primitive.attached({ chart: {}, series: { priceToCoordinate: (price: number) => 200 - price }, requestUpdate() {} } as unknown as SeriesAttachedParameter);
    primitive.setState(bridge, false);
    const renderer = primitive.paneViews()[0].renderer()!;
    const draw = () => renderer.draw({ useMediaCoordinateSpace: (callback: (scope: unknown) => void) => callback({ context, mediaSize: { width: 390, height: 200 } }) } as unknown as Parameters<typeof renderer.draw>[0]);
    assert.equal(receipts.length, 0); draw(); await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(receipts[0].status, 'rendered');
    assert.ok(calls.includes('rect:0,0,390,200'));
    assert.equal(primitive.hitTest(20, 100)?.externalId, 'forecast:forecast');
    assert.deepEqual(record, original);
    draw(); await new Promise((resolve) => setTimeout(resolve, 0)); assert.equal(receipts.length, 1);
    primitive.setState({ ...bridge, hidden: new Set(['forecast']) }, false); draw(); await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(receipts[1].status, 'hidden'); assert.equal(primitive.hitTest(20, 100), null);
    primitive.setState(bridge, true); await new Promise((resolve) => setTimeout(resolve, 0)); assert.match(receipts[2].reason!, /comparison/);
    let attempts = 0;
    primitive.setState({ ...bridge, records: [{ ...record, revision: 2 }], onRendered: async (receipt) => {
      attempts += 1; if (attempts === 1) throw new Error('Disconnected'); receipts.push(receipt);
    } }, false);
    draw(); await new Promise((resolve) => setTimeout(resolve, 0));
    draw(); await new Promise((resolve) => setTimeout(resolve, 0));
    assert.equal(attempts, 1, 'Failed receipts cannot spin on chart repaint');
    const now = Date.now;
    try {
      Date.now = () => now() + 6000;
      draw(); await new Promise((resolve) => setTimeout(resolve, 0));
      assert.equal(attempts, 2, 'The same revision retries after a transient disconnect');
      assert.equal(receipts.at(-1)?.status, 'rendered');
    } finally { Date.now = now; }
    primitive.detached();
  } finally { if (oldDocument) Object.defineProperty(globalThis, 'document', oldDocument); else Reflect.deleteProperty(globalThis, 'document'); }
});

test('forecast transport keeps explicit admission and exact evidence selection separate from reads', async () => {
  const calls: { method: string; params: Record<string, unknown> }[] = [];
  const api = createMarketForecastApi(async <T extends Record<string, unknown>>(method: string, params: Record<string, unknown>) => {
    calls.push({ method, params }); return {} as T;
  });
  await api.list('document'); await api.get('forecast'); await api.evidence('forecast', 'evidence');
  assert.ok(calls.every((call) => call.method !== 'market.forecast.request'));
  const request = { requestId: 'stable', sessionKey: 'chart', observationId: 'frozen', documentId: 'document', provider: 'test', model: 'test-model', detail: 'balanced' as const, paired: true, entryExpirySessions: 10 };
  await api.request(request); await api.request(request);
  assert.deepEqual(calls.at(-1), calls.at(-2));
  assert.deepEqual(calls[2], { method: 'market.forecast.get', params: { forecastId: 'forecast', evidenceId: 'evidence' } });
});

test('terminal forecast attempts cannot describe themselves as still generating', () => {
  const record = forecast(); record.members = {};
  for (const status of ['failed', 'cancelled', 'no_setup'] as const) {
    record.status = status; assert.doesNotMatch(forecastThesis(record), /Generating/);
  }
});
