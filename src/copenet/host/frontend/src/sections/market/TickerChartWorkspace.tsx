import { useEffect, useMemo, useState } from 'react';
import { CandleChart } from './CandleChart';
import { ChartComparisonControl } from './ChartComparisonControl';
import { ChartEvidenceControl, type InsiderDisplayMode, type InsiderLookback } from './ChartEvidenceControl';
import { buildComparisonLines, comparisonSearch, comparisonStateFromSearch } from './chartComparison';
import { FinancialOverlayControls, FinancialOverlayStatus, type OverlayMetric } from './FinancialOverlayUi';
import { observationTime, snapOverlayToCandles } from './financialOverlay';
import { MarketChartToolbar, type ChartRange, type ChartTimeframe } from './MarketChartToolbar';
import { MM, PanelCard } from './marketUi';
import { PriceAlertControl } from './PriceAlertControl';
import type { ChartEvent, EvidenceItem, FinancialFrequency, Ohlcv, TickerDetailPayload } from './types';
import { isValuationPayload } from './types';
import { useChartComparisons } from './useChartComparisons';
import { isValuationMetric, metricInfo, useFinancialMetrics } from './useFinancialMetrics';
import { useFinancialSeries } from './useFinancialSeries';
import { usePriceAlerts } from './usePriceAlerts';
import { useIsMobile } from '../../lib/responsive';
import { readTickerChartViewState, writeTickerChartViewState } from './tickerChartViewState';

const RANGE_SECONDS: Record<Exclude<ChartRange, 'MAX'>, number> = {
  '6M': 183 * 86400,
  '1Y': 366 * 86400,
  '3Y': 3 * 366 * 86400,
  '5Y': 5 * 366 * 86400,
};

function visibleBars(bars: Ohlcv[], range: ChartRange): Ohlcv[] {
  if (range === 'MAX' || bars.length === 0) return bars;
  const cutoff = bars[bars.length - 1].t - RANGE_SECONDS[range];
  return bars.filter((bar) => bar.t >= cutoff);
}

function formatQuote(value?: number | null): string {
  return value == null ? '—' : value.toLocaleString(undefined, { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 4 });
}

function formatBarDate(value?: number | null): string {
  if (!value) return 'bar date unavailable';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(value * 1000));
}

function formatVolume(value: number): string {
  if (value >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(2)}B`;
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(2)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return value.toLocaleString();
}

export function TickerChartWorkspace({ detail, events, evidence }: { detail: TickerDetailPayload; events: ChartEvent[]; evidence: EvidenceItem[] }) {
  const isMobile = useIsMobile();
  const [initialView] = useState(readTickerChartViewState);
  const [timeframe, setTimeframe] = useState<ChartTimeframe>(initialView.timeframe);
  const [range, setRange] = useState<ChartRange>(initialView.range);
  const [overlayMetric, setOverlayMetric] = useState<OverlayMetric | null>(initialView.overlayMetric);
  const [overlayFrequency, setOverlayFrequency] = useState<FinancialFrequency>(initialView.overlayFrequency);
  const [alertPlacementActive, setAlertPlacementActive] = useState(false);
  const [pickedAlertPrice, setPickedAlertPrice] = useState<number | null>(null);
  const [showInsiderTransactions, setShowInsiderTransactions] = useState(initialView.showInsiderTransactions);
  const [insiderLookback, setInsiderLookback] = useState<InsiderLookback>(initialView.insiderLookback);
  const [insiderDisplayMode, setInsiderDisplayMode] = useState<InsiderDisplayMode>(initialView.insiderDisplayMode);
  const [logScale, setLogScale] = useState(() => {
    try { return localStorage.getItem('mm-log-scale') === '1'; } catch { return false; }
  });
  const [comparisonExpressions, setComparisonExpressions] = useState(() => comparisonStateFromSearch(window.location.search).expressions);
  const [comparisonMode, setComparisonMode] = useState(() => comparisonStateFromSearch(window.location.search).active);
  const effectiveComparisonExpressions = useMemo(
    () => comparisonExpressions.filter((expression) => expression !== detail.symbol),
    [comparisonExpressions, detail.symbol],
  );
  const priceAlerts = usePriceAlerts(detail.symbol);
  const overlayMetrics = useFinancialMetrics();
  const overlayIsValuation = isValuationMetric(overlayMetrics, overlayMetric);
  const overlayFrequencyChoices = metricInfo(overlayMetrics, overlayMetric)?.frequencies;
  const effectiveOverlayFrequency: FinancialFrequency = overlayIsValuation ? 'ttm' : overlayFrequencyChoices && !overlayFrequencyChoices.includes(overlayFrequency) ? overlayFrequencyChoices[0] : overlayFrequency;
  const overlaySeries = useFinancialSeries(detail.symbol, overlayMetric ?? 'revenue', effectiveOverlayFrequency, overlayMetric != null);

  const rawBars = timeframe === 'D' ? detail.series.daily : timeframe === 'M' ? detail.series.monthly : detail.series.weekly;
  const bars = useMemo(() => visibleBars(rawBars, range), [rawBars, range]);
  const comparisons = useChartComparisons(effectiveComparisonExpressions, timeframe);
  const comparisonLines = useMemo(() => buildComparisonLines(detail.symbol, bars, effectiveComparisonExpressions, comparisons.payload?.series ?? []), [bars, effectiveComparisonExpressions, comparisons.payload?.series, detail.symbol]);
  const overlayPoints = useMemo(() => {
    if (!overlayMetric || !overlaySeries.data || bars.length === 0) return undefined;
    const raw = isValuationPayload(overlaySeries.data)
      ? overlaySeries.data.observations.map((item) => ({ t: Math.floor(Date.parse(`${item.timestamp}T00:00:00Z`) / 1000), value: item.value != null && Number.isFinite(item.value) ? item.value : null }))
      : overlaySeries.data.observations.filter((item) => item.availableAt && Number.isFinite(item.value)).map((item) => ({ t: observationTime(item), value: item.value }));
    return snapOverlayToCandles(raw, bars.map((bar) => bar.t));
  }, [bars, overlayMetric, overlaySeries.data]);

  useEffect(() => {
    if (effectiveComparisonExpressions.length !== comparisonExpressions.length) {
      setComparisonExpressions(effectiveComparisonExpressions);
      if (!effectiveComparisonExpressions.length) setComparisonMode(false);
      return;
    }
    const search = comparisonSearch(effectiveComparisonExpressions, comparisonMode && effectiveComparisonExpressions.length > 0);
    window.history.replaceState({}, '', `${window.location.pathname}${search}`);
  }, [comparisonExpressions, comparisonMode, detail.symbol, effectiveComparisonExpressions]);

  useEffect(() => {
    try { localStorage.setItem('mm-log-scale', logScale ? '1' : '0'); } catch { /* optional preference */ }
  }, [logScale]);

  useEffect(() => {
    writeTickerChartViewState({ timeframe, range, overlayMetric, overlayFrequency, showInsiderTransactions, insiderLookback, insiderDisplayMode });
  }, [timeframe, range, overlayMetric, overlayFrequency, showInsiderTransactions, insiderLookback, insiderDisplayMode]);

  const latest = bars[bars.length - 1]?.t;
  const lookbackDays = insiderLookback === '90D' ? 90 : insiderLookback === '1Y' ? 366 : insiderLookback === '3Y' ? 3 * 366 : insiderLookback === '5Y' ? 5 * 366 : null;
  const chartEvidence = evidence.filter((item) => {
    if (item.type !== 'Insider') return true;
    if (!showInsiderTransactions) return false;
    if (insiderLookback === 'chart') return item.t == null || bars.length === 0 || item.t >= bars[0].t;
    return lookbackDays == null || latest == null || item.t == null || item.t >= latest - lookbackDays * 86400;
  });
  const chartEventRows = events.filter((event) => {
    if (event.kind !== 'insider') return true;
    if (!showInsiderTransactions) return false;
    if (insiderLookback === 'chart') return bars.length === 0 || event.t >= bars[0].t;
    return lookbackDays == null || latest == null || event.t >= latest - lookbackDays * 86400;
  });
  const overlayUnit = !overlaySeries.data ? undefined : isValuationPayload(overlaySeries.data) ? 'ratio' : overlaySeries.data.observations[0]?.unit;
  const latestVisibleBar = bars[bars.length - 1];
  const showingComparison = comparisonMode && effectiveComparisonExpressions.length > 0;
  const viewportHeight = typeof window === 'undefined' ? 900 : window.innerHeight;
  const chartHeight = isMobile ? 430 : viewportHeight < 780 ? 320 : viewportHeight < 900 ? 400 : 500;
  const removeComparison = (expression: string) => setComparisonExpressions((current) => {
    const next = current.filter((item) => item !== expression);
    if (!next.length) setComparisonMode(false);
    return next;
  });

  return (
    <PanelCard title={`${showingComparison ? 'Indexed comparison' : 'Price'} · ${timeframe === 'D' ? 'Daily' : timeframe === 'M' ? 'Monthly' : 'Weekly'} bars · ${range === 'MAX' ? 'Max history' : range}`} status={comparisons.error && showingComparison ? 'error' : bars.length ? 'live' : 'error'} headerLayout="chart-toolbar" right={
      <MarketChartToolbar
        timeframe={timeframe}
        onTimeframe={setTimeframe}
        range={range}
        onRange={setRange}
        alertControl={showingComparison ? null : <PriceAlertControl alerts={priceAlerts.alerts} currentPrice={detail.quote.price ?? 0} pickedPrice={pickedAlertPrice} placing={alertPlacementActive} loading={priceAlerts.loading} error={priceAlerts.error} onStartPlacing={() => setAlertPlacementActive(true)} onStopPlacing={() => { setAlertPlacementActive(false); setPickedAlertPrice(null); }} onCreate={async (direction, threshold) => { const created = await priceAlerts.create(direction, threshold, detail.quote.price ?? 0); if (created) setPickedAlertPrice(null); return created; }} onCancel={priceAlerts.cancel} />}
        financialControls={showingComparison ? null : <FinancialOverlayControls metrics={overlayMetrics} metric={overlayMetric} frequency={effectiveOverlayFrequency} loading={overlaySeries.loading} onMetric={setOverlayMetric} onFrequency={setOverlayFrequency} />}
        comparisonControl={<ChartComparisonControl active={showingComparison} expressions={effectiveComparisonExpressions} onActive={setComparisonMode} onAdd={(expression) => setComparisonExpressions((current) => [...current, expression])} onRemove={removeComparison} onClear={() => { setComparisonExpressions([]); setComparisonMode(false); }} />}
        evidenceControl={showingComparison ? null : <ChartEvidenceControl showInsiderTransactions={showInsiderTransactions} onShowInsiderTransactions={setShowInsiderTransactions} lookback={insiderLookback} onLookback={setInsiderLookback} displayMode={insiderDisplayMode} onDisplayMode={setInsiderDisplayMode} />}
        logScale={logScale}
        onLogScale={setLogScale}
      />
    }>
      {!showingComparison && latestVisibleBar && (
        <div aria-label="Latest plotted bar" className="ticker-chart-ohlc">
          <span>{formatBarDate(latestVisibleBar.t)}</span><span>O <b>{formatQuote(latestVisibleBar.o)}</b></span><span>H <b>{formatQuote(latestVisibleBar.h)}</b></span><span>L <b>{formatQuote(latestVisibleBar.l)}</b></span><span>C <b>{formatQuote(latestVisibleBar.c)}</b></span><span>V <b>{formatVolume(latestVisibleBar.v)}</b></span>
        </div>
      )}
      {showingComparison && <ComparisonLegend labels={[detail.symbol, ...comparisonExpressions.filter((item) => item !== detail.symbol)]} lines={comparisonLines} loading={comparisons.loading} error={comparisons.error} />}
      <CandleChart bars={bars} events={chartEventRows} evidence={chartEvidence} height={chartHeight} financialOverlay={overlayPoints} financialOverlayKind={overlayMetric ?? undefined} financialOverlayUnit={overlayUnit} financialOverlayValuation={overlayIsValuation} financialOverlayInverted={overlaySeries.data != null && isValuationPayload(overlaySeries.data) && overlaySeries.data.inverted === true} priceAlerts={priceAlerts.alerts} draftAlertPrice={pickedAlertPrice} alertPlacementActive={alertPlacementActive} onAlertPriceSelected={(price) => { setPickedAlertPrice(price); setAlertPlacementActive(false); }} comparisonMode={showingComparison} comparisonLines={comparisonLines} insiderDisplayMode={insiderDisplayMode} logScale={logScale} />
      {!showingComparison && <FinancialOverlayStatus metrics={overlayMetrics} metric={overlayMetric} state={overlaySeries} />}
      <div className="ticker-chart-footer"><span>{showingComparison ? 'Every line is rebased to 0% at its first observation in the visible range.' : `8-K and Form 144 markers on · Form 4 ${showInsiderTransactions ? `on (${insiderDisplayMode})` : 'off'}`}</span><span>{bars.length.toLocaleString()} bars · split-adjusted traded price</span></div>
    </PanelCard>
  );
}

function ComparisonLegend({ labels, lines, loading, error }: { labels: string[]; lines: ReturnType<typeof buildComparisonLines>; loading: boolean; error: string | null }) {
  if (error) return <div role="alert" style={{ paddingBottom: 8, color: MM.down, fontSize: 11 }}>{error}</div>;
  const byLabel = new Map(lines.map((line) => [line.label, line]));
  return (
    <div className="ticker-comparison-legend" aria-label="Comparison legend">
      {labels.map((label) => {
        const line = byLabel.get(label);
        if (!line) return <span key={label}><b>{label}</b> {loading ? 'loading…' : 'no overlapping history'}</span>;
        const value = line.data[line.data.length - 1]?.value;
        return <span key={line.id} style={{ color: line.color }}><b>{line.label}</b> {value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(1)}%`}</span>;
      })}
      <em>Overlays, event markers, and price alerts are paused in comparison mode.</em>
    </div>
  );
}
