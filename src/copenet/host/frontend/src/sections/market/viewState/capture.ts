import type { ChartDocument, ChartSelection, ChartViewport, InstrumentRef, MarketCapture, ViewResource } from '../chartAgent/types';
import type { TickerIntelligence } from '../types';
import type { useTickerViewModel } from '../useTickerViewModel';

export function instrumentFor(symbol: string, assetClass = 'equity'): InstrumentRef {
  return { instrumentId: `yahoo:${symbol}`, symbol, assetClass, source: 'yahoo', currency: null };
}

export function publicIntelligence(intelligence: TickerIntelligence | null | undefined) {
  if (!intelligence) return null;
  const { asOf, assetRole, trend, momentum, returns, drawdown, volatility, relativeStrength, structure, dataQuality, rotation, exposure } = intelligence;
  return { asOf, assetRole, trend, momentum, returns, drawdown, volatility, relativeStrength, structure, dataQuality, rotation, exposure };
}

export function captureTickerView(options: {
  view: ReturnType<typeof useTickerViewModel>;
  document: ChartDocument;
  viewId: string;
  revision: number;
  viewport: ChartViewport;
  selection: ChartSelection | null;
  contributions: ViewResource[];
  includeAccountContext: boolean;
}): MarketCapture {
  const { view, document, viewport, contributions } = options;
  const detail = view.detail;
  if (!detail || detail.symbol !== document.instrument.symbol) throw new Error('Wait for this ticker’s chart document to load.');
  if (viewport.from == null || viewport.to == null) throw new Error('Wait for the chart to establish its visible range.');
  const resources: ViewResource[] = [];
  for (const [seriesKey, timeframe] of [['daily', 'D'], ['weekly', 'W'], ['monthly', 'M']] as const) {
    const rows = detail.series[seriesKey];
    resources.push({ key: `candles:${timeframe}`, kind: 'candles', label: `${detail.symbol} ${timeframe} candles`,
      status: view.ticker.stale ? 'stale' : rows.length ? 'loaded' : 'empty', observedAt: detail.asOf,
      rows: rows.map((bar) => ({ ...bar })), metadata: { timeframe, timestampUnit: 'seconds', priceBasis: detail.quote.priceBasis, source: 'yahoo',
        completeness: 'Latest daily/weekly/monthly candle may be forming; do not infer completion from capture time.' } });
  }
  for (const indicator of view.computedIndicators) {
    const outputs = indicator.outputs.map((output) => ({ output, values: new Map(output.points.map((point) => [point.t, point.value])) }));
    resources.push({ key: `indicator:${indicator.instanceId}`, kind: 'indicator', label: indicator.label,
      status: indicator.insufficientHistory ? 'empty' : 'loaded', observedAt: detail.asOf,
      rows: view.bars.map((bar) => ({ t: bar.t, ...Object.fromEntries(outputs.map(({ output, values }) => [output.key, values.get(bar.t) ?? null])) })),
      metadata: { indicatorId: indicator.indicatorId, config: indicator.instance.config, timeframe: view.timeframe,
        visible: indicator.visible && !view.comparing, placement: indicator.placement, source: 'chart_indicator_registry',
        outputs: indicator.outputs.map(({ key, label, plot, color, lineWidth, lineStyle, latest }) => ({ key, label, plot, color, lineWidth, lineStyle, latest })),
        references: indicator.references, paneRange: indicator.paneRange, timestampUnit: 'seconds',
        historyBars: view.rawBars.length, warmup: 'Computed over full loaded history before slicing' } });
  }
  resources.push({ key: 'ticker:overview', kind: 'panel', label: 'Ticker overview', status: 'loaded', observedAt: detail.asOf,
    rows: [{ quote: detail.quote, stats: detail.stats, intelligence: publicIntelligence(detail.intelligence), verdict: detail.verdict, signals: detail.signals, insight: detail.insight, kill: detail.kill }],
    metadata: { active: view.tab === 'overview' && view.snap !== 'collapsed' } });
  resources.push({ key: 'chart:evidence', kind: 'evidence', label: 'Chart SEC events', status: view.chartEvidence.length ? 'loaded' : 'empty',
    observedAt: view.sec.payload?.asOf ?? detail.asOf, rows: view.chartEvidence.map((row) => ({ ...row })),
    metadata: { events: view.chartEventRows, showInsider: view.showInsider, lookback: view.insiderLookback, display: view.insiderDisplay } });
  if (view.overlayMetric) resources.push({ key: 'chart:financial', kind: 'financial', label: view.overlayMetric, unit: view.overlaySeries.data?.observations[0]?.unit,
    status: view.overlaySeries.error ? 'stale' : view.overlaySeries.data ? 'loaded' : 'not-loaded',
    rows: view.overlayPoints?.map((row) => ({ ...row })) ?? [], metadata: { frequency: view.effectiveFrequency,
      visible: !view.comparing, alignment: view.overlayIsValuation ? 'price_timestamp' : 'availability', timestampUnit: 'seconds', observations: view.overlaySeries.data?.observations ?? [], error: view.overlaySeries.error } });
  for (const comparison of view.comparisonLines) resources.push({ key: `comparison:${comparison.id}`, kind: 'comparison',
    label: comparison.label, unit: comparison.valueMode === 'percent' ? 'percent' : 'number', status: 'loaded', rows: comparison.data.map((row) => ({ ...row })), metadata: { valueMode: comparison.valueMode, color: comparison.color, timestampUnit: 'seconds' } });
  resources.push({ key: 'chart:drawings', kind: 'drawings', label: 'Drawings at capture', status: document.objects.length ? 'loaded' : 'empty',
    rows: document.objects.map((object) => ({ ...object })), metadata: { documentId: document.documentId, revision: document.revision } });
  if (detail.intelligence?.portfolio) resources.push({ key: 'account:position', kind: 'panel', label: 'Position in this ticker',
    status: 'loaded', rows: [{ ...detail.intelligence.portfolio }], metadata: { accountContext: true } });
  resources.push(...contributions);
  const requiredPanel = view.snap === 'collapsed' || view.tab === 'overview' ? null : `panel:${view.tab}`;
  if (requiredPanel && !contributions.some((resource) => resource.key === requiredPanel)) {
    throw new Error('The visible research panel is still updating. Try sending again when it is ready.');
  }
  if (!contributions.some((resource) => resource.key === 'quote:displayed')) {
    throw new Error('The displayed quote is still updating. Try sending again when it is ready.');
  }
  if (new Set(resources.map((resource) => resource.key)).size !== resources.length) {
    throw new Error('Chart resources changed during capture. Wait for the view to settle and try again.');
  }
  const scopedResources = resources.map((resource) => resource.metadata.accountContext && !options.includeAccountContext
    ? { ...resource, status: 'not-loaded' as const, rows: [], metadata: { accountContext: true, excluded: 'Account context is off' } }
    : resource);
  // Serialization is the snapshot boundary: subsequent UI edits cannot mutate this turn.
  return JSON.parse(JSON.stringify({ schemaVersion: 1, viewId: options.viewId, viewRevision: options.revision,
    instrument: document.instrument, timeframe: view.timeframe, range: view.range, viewport,
    selection: options.selection, settings: { logScale: view.logScale, comparisonMode: view.comparing, showVolume: view.showVolume,
      researchTab: view.tab, researchOpen: view.snap !== 'collapsed', includeAccountContext: options.includeAccountContext,
      requestedSymbol: view.normalized, displayedSymbol: detail.symbol, indicators: view.indicators },
    resources: scopedResources, documentId: document.documentId, documentRevision: document.revision }, (_key, value) => {
    if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('Chart data contains a nonfinite value. Refresh the affected resource before sending.');
    return value;
  }));
}
