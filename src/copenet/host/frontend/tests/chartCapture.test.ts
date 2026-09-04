import assert from 'node:assert/strict';
import test from 'node:test';
import { captureTickerView, instrumentFor } from '../src/sections/market/viewState/capture';
import { ViewResources } from '../src/sections/market/viewState/resources';
import type { ViewResource } from '../src/sections/market/chartAgent/types';

type CaptureOptions = Parameters<typeof captureTickerView>[0];

function fixture(): CaptureOptions {
  const daily = [100, 200, 300].map((t, index) => ({ t, o: 8 + index, h: 10 + index, l: 7 + index, c: 9.123456789 + index, v: index * 100 }));
  const weekly = [{ ...daily[0], c: 19.987654321, v: 12345 }];
  const monthly = [{ ...daily[0], c: 29.123456789, v: 45678 }];
  const indicator = {
    instanceId: 'rsi-one', indicatorId: 'rsi', label: 'RSI 14', visible: true, placement: 'pane', insufficientHistory: false,
    instance: { id: 'rsi-one', indicatorId: 'rsi', config: { period: 14 } },
    definition: { compute: () => { throw new Error('Capture must never recompute indicators'); } },
    outputs: [{ key: 'rsi', label: 'RSI', plot: 'line', color: '#fb9423', lineWidth: 2, lineStyle: 'solid', latest: '64.2', points: [{ t: 200, value: 64.23456789 }] }],
    references: [{ value: 70 }], paneRange: { min: 0, max: 100 },
  };
  const view = {
    detail: { symbol: 'SYN', asOf: '2026-01-01T00:00:00Z', series: { daily, weekly, monthly },
      quote: { price: 11.123456789, changePct: null, priceBasis: 'split_adjusted', comparison: 'previous_daily_bar' },
      intelligence: { asOf: '2026-01-01T00:00:00Z', assetRole: 'equity', trend: { longTrend: 'rising' }, returns: { r1wPct: 1.234567 },
        dataQuality: { historyWeeks: 100, hasVolume: true, thinHistory: false }, portfolio: { shares: 777000123, avgCost: 456.789, source: 'synthetic-account' } },
      stats: { yearLow: 7 }, verdict: [], signals: [], insight: { softBottoming: true, score: 0.1234567 }, kill: 'Below the selected low',
    },
    ticker: { stale: false }, normalized: 'SYN', timeframe: 'D', range: '1Y', bars: daily, rawBars: daily,
    computedIndicators: [indicator], indicators: [indicator.instance], tab: 'overview', snap: 'half',
    sec: { payload: null }, chartEvidence: [], chartEventRows: [], showInsider: false, insiderLookback: 'chart', insiderDisplay: 'clusters',
    overlayMetric: null, overlaySeries: { data: null, error: null }, overlayPoints: undefined,
    effectiveFrequency: 'quarterly', overlayIsValuation: false, comparisonLines: [], comparing: false, logScale: false, showVolume: true,
  } as unknown as CaptureOptions['view'];
  return { view, document: { documentId: 'synthetic-document', workspaceId: 'primary', instrument: instrumentFor('SYN'), revision: 3,
    objects: [{ id: 'level-test', kind: 'level', anchors: [{ t: 100, value: 7.23456789 }], timeframe: 'D', label: 'Exact level', color: '#fb9423', visible: true, rationale: '', evidence: [], owner: { kind: 'operator' } }] },
    viewId: 'synthetic-view', revision: 12, viewport: { from: 100, to: 300, logicalFrom: -0.25, logicalTo: 3.5 }, selection: { from: 200, to: 200 },
    includeAccountContext: false,
    contributions: [{ key: 'quote:displayed', kind: 'quote', label: 'Displayed quote', status: 'loaded',
      observedAt: '2026-01-01T00:00:05Z', rows: [{ price: 12.987654321, dayVolume: null }], metadata: { source: 'yahoo_stream' } }],
  };
}

function resource(options: ReturnType<typeof captureTickerView>, key: string) {
  const value = options.resources.find((item) => item.key === key);
  assert.ok(value, `${key} must be captured`);
  return value;
}

test('capture uses canonical D/W/M identities and the exact rendered candle and indicator values', () => {
  const options = fixture();
  const capture = captureTickerView(options);
  assert.deepEqual(capture.resources.filter((row) => row.kind === 'candles').map((row) => row.key), ['candles:D', 'candles:W', 'candles:M']);
  for (const [timeframe, source] of [['D', 'daily'], ['W', 'weekly'], ['M', 'monthly']] as const) {
    assert.deepEqual(resource(capture, `candles:${timeframe}`).rows, options.view.detail!.series[source]);
    assert.equal(resource(capture, `candles:${timeframe}`).metadata.timeframe, timeframe);
    assert.equal(resource(capture, `candles:${timeframe}`).metadata.priceBasis, 'split_adjusted');
    assert.equal(resource(capture, `candles:${timeframe}`).metadata.timestampUnit, 'seconds');
  }
  assert.deepEqual(resource(capture, 'indicator:rsi-one').rows, [
    { t: 100, rsi: null }, { t: 200, rsi: 64.23456789 }, { t: 300, rsi: null },
  ]);
  assert.equal(resource(capture, 'indicator:rsi-one').metadata.historyBars, 3);
  assert.deepEqual(capture.viewport, options.viewport);
  assert.deepEqual(capture.selection, options.selection);
  assert.equal(resource(capture, 'ticker:overview').rows[0].kill, 'Below the selected low');
  assert.deepEqual(resource(capture, 'ticker:overview').rows[0].insight, { softBottoming: true, score: 0.1234567 });
});

test('new prices, viewport, interval and config enter the next capture without changing earlier evidence', () => {
  const options = fixture();
  const first = captureTickerView(options);
  options.contributions[0].rows[0].price = 13.123456789;
  options.viewport.logicalTo = 8.5;
  options.view.timeframe = 'W';
  options.view.computedIndicators[0].instance.config.period = 21;
  options.document.objects[0].anchors[0].value = 5;
  const second = captureTickerView(options);
  assert.equal(resource(first, 'quote:displayed').rows[0].price, 12.987654321);
  assert.equal(resource(second, 'quote:displayed').rows[0].price, 13.123456789);
  assert.equal(first.timeframe, 'D');
  assert.equal(second.timeframe, 'W');
  assert.equal(first.viewport.logicalTo, 3.5);
  assert.equal(second.viewport.logicalTo, 8.5);
  assert.deepEqual(resource(first, 'indicator:rsi-one').metadata.config, { period: 14 });
  assert.equal((resource(first, 'chart:drawings').rows[0].anchors as { value: number }[])[0].value, 7.23456789);
});

test('account exclusion covers every resource body and nested metadata while preserving public analysis', () => {
  const options = fixture();
  options.contributions.push({ key: 'panel:synthesis', kind: 'panel', label: 'Saved model synthesis', status: 'loaded',
    rows: [{ read: 'SYNTHETIC_ACCOUNT_SECRET' }], metadata: { accountContext: true, nested: { text: 'SYNTHETIC_ACCOUNT_SECRET' } } });
  const excluded = captureTickerView(options);
  assert.ok(!JSON.stringify(excluded).includes('SYNTHETIC_ACCOUNT_SECRET'));
  assert.ok(!JSON.stringify(excluded).includes('777000123'));
  assert.deepEqual(resource(excluded, 'account:position').rows, []);
  assert.equal(resource(excluded, 'panel:synthesis').metadata.excluded, 'Account context is off');
  assert.deepEqual((resource(excluded, 'ticker:overview').rows[0].intelligence as { returns: object }).returns, { r1wPct: 1.234567 });
  options.includeAccountContext = true;
  const included = captureTickerView(options);
  assert.equal(resource(included, 'account:position').rows[0].shares, 777000123);
  assert.equal(resource(included, 'panel:synthesis').rows[0].read, 'SYNTHETIC_ACCOUNT_SECRET');
});

test('visible research filters, financial source detail and comparison values survive capture exactly', () => {
  const options = fixture();
  options.view.tab = 'fundamentals';
  options.view.overlayMetric = 'trailing_pe';
  options.view.overlayIsValuation = true;
  options.view.overlayPoints = [{ t: 100, value: 19.123456789 }];
  options.view.comparisonLines = [{ id: 'peer', label: 'SYN/PEER', valueMode: 'percent', color: '#fb9423', data: [{ t: 100, value: 0 }, { t: 200, value: 12.23456789 }] }];
  options.view.comparing = true;
  const sourceRows = Array.from({ length: 2000 }, (_, index) => ({ timestamp: index, value: index / 17, availableAt: '2025-01-03' }));
  const panel: ViewResource = { key: 'panel:fundamentals', kind: 'panel', label: 'Financial explorer', status: 'loaded', rows: [{ timestamp: 123, revenue: 12.3456789 }],
    metadata: { storyId: 'income', frequency: 'quarterly', alignment: 'period-end', visibleMetrics: ['revenue'], sourceObservations: sourceRows } };
  options.contributions.push(panel);
  const captured = captureTickerView(options);
  assert.deepEqual(resource(captured, 'panel:fundamentals'), panel);
  assert.equal((resource(captured, 'panel:fundamentals').metadata.sourceObservations as object[]).length, 2000);
  assert.deepEqual(resource(captured, 'comparison:peer').rows, options.view.comparisonLines[0].data);
  assert.equal(resource(captured, 'chart:financial').metadata.alignment, 'price_timestamp');
  assert.equal(resource(captured, 'chart:financial').metadata.visible, false);
  assert.equal(resource(captured, 'indicator:rsi-one').metadata.visible, false);
});

test('capture fails rather than silently omit the displayed panel/quote or mix ticker generations', () => {
  const options = fixture();
  options.view.tab = 'evidence';
  assert.throws(() => captureTickerView(options), /visible research panel/);
  options.view.snap = 'collapsed';
  options.contributions = [];
  assert.throws(() => captureTickerView(options), /displayed quote/);
  options.view.detail!.symbol = 'OTHER';
  assert.throws(() => captureTickerView(options), /chart document/);
});

test('nonfinite renderer values do not silently become null gaps during serialization', () => {
  const options = fixture();
  options.view.detail!.series.daily[0].c = Number.NaN;
  assert.throws(() => captureTickerView(options), /nonfinite value/);
});

test('late contribution cleanup cannot erase a newer generation or expose a different ticker', () => {
  const resources = new ViewResources();
  const oldQuote = fixture().contributions[0];
  const removeOld = resources.set('SYN', oldQuote);
  const newQuote = { ...oldQuote, rows: [{ price: 19.123456 }] };
  resources.set('OTHER', newQuote);
  removeOld();
  assert.deepEqual(resources.read('SYN'), []);
  assert.deepEqual(resources.read('OTHER'), [newQuote]);
  const latest = { ...oldQuote, rows: [{ price: 21.234567 }] };
  resources.set('OTHER', latest);
  assert.deepEqual(resources.read('OTHER'), [latest]);
});

test('financial contribution declares actual alignment, units and unrounded table rows for each story', async () => {
  const { financialPanelResource } = await import('../src/sections/market/viewState/panelResources');
  const input = { story: { id: 'valuation', valueKind: 'multiple', metrics: [{ id: 'trailing_pe' }] }, frequency: 'ttm', active: true,
    visibleMetrics: new Set(['trailing_pe']), rows: [{ timestamp: 1234567000, trailing_pe: 21.1234567 }],
    series: [{ observations: [{ timestamp: '2025-03-01', value: 21.1234567, unit: 'ratio' }] }], loading: false, errors: [], warnings: [],
  } as unknown as Parameters<typeof financialPanelResource>[0];
  const result = financialPanelResource(input);
  assert.equal(result.metadata.alignment, 'quarterly_last_price_timestamp');
  assert.equal(result.metadata.timestampUnit, 'milliseconds');
  assert.deepEqual(result.metadata.units, [{ metric: 'trailing_pe', unit: 'ratio' }]);
  assert.deepEqual(result.rows, input.rows);
  assert.equal(result.status, 'loaded');
  input.story.id = 'income';
  input.frequency = 'annual';
  input.errors = ['Synthetic failure'];
  const annual = financialPanelResource(input);
  assert.equal(annual.metadata.alignment, 'period-end');
  assert.equal(annual.metadata.frequency, 'annual');
  assert.equal(annual.status, 'stale');
});

test('SEC contribution preserves the selected day, history depth and exact displayed evidence', async () => {
  const { evidencePanelResource } = await import('../src/sections/market/viewState/panelResources');
  const input = { visibleEvidence: [{ t: 123, note: 'Synthetic issuer filing' }], selectedDay: '2026-01-01', insiderWindows: [],
    depthDays: 365, active: true, showMethod: true, loading: false, error: null, asOf: '2026-01-02T00:00:00Z', warnings: [],
  } as unknown as Parameters<typeof evidencePanelResource>[0];
  const result = evidencePanelResource(input);
  assert.deepEqual(result.rows, input.visibleEvidence);
  assert.equal(result.metadata.selectedDay, input.selectedDay);
  assert.equal(result.metadata.depthDays, 365);
  assert.equal(result.metadata.timestampUnit, 'seconds');
  assert.equal(result.metadata.showMethod, true);
  assert.equal(evidencePanelResource({ ...input, visibleEvidence: [], loading: true }).status, 'not-loaded');
});
