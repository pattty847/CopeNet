import { useEffect, useMemo, useState } from 'react';
import { ArrowLeft, RefreshCw, Search } from 'lucide-react';
import { CandleChart } from './CandleChart';
import { FinancialOverlayControls, FinancialOverlayStatus, type OverlayMetric } from './FinancialOverlayUi';
import { MarketChartToolbar, type ChartRange, type ChartTimeframe } from './MarketChartToolbar';
import { MM, PanelCard, toneColor } from './marketUi';
import { observationTime, snapOverlayToCandles } from './financialOverlay';
import { isValuationMetric, metricInfo, useFinancialMetrics } from './useFinancialMetrics';
import { useFinancialSeries } from './useFinancialSeries';
import { usePriceAlerts } from './usePriceAlerts';
import { isValuationPayload, type FinancialFrequency, type Ohlcv } from './types';
import { TickerEvidencePanel } from './TickerEvidencePanel';
import { TickerOverviewRail } from './TickerOverviewRail';
import { TickerReadPanel } from './TickerReadPanel';
import { TickerSignalPanel } from './TickerSignalPanel';
import { PriceAlertControl } from './PriceAlertControl';
import { useTickerDetail, useTickerEvidence, type MarketWatchlistState } from './useMarketMonitorData';
import { useIsMobile } from '../../lib/responsive';
import { ChartComparisonControl } from './ChartComparisonControl';
import { ChartEvidenceControl, type InsiderDisplayMode, type InsiderLookback } from './ChartEvidenceControl';
import { buildComparisonLines, comparisonSearch, comparisonStateFromSearch } from './chartComparison';
import { useChartComparisons } from './useChartComparisons';
import { useAppStore } from '../../store/useAppStore';

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

export function TickerDetailPage({ symbol, onClose, watchlist }: { symbol: string; onClose: () => void; watchlist: MarketWatchlistState }) {
  const ticker = useTickerDetail(symbol);
  const sec = useTickerEvidence(symbol);
  const isMobile = useIsMobile();
  const setCommandPaletteOpen = useAppStore((state) => state.setCommandPaletteOpen);
  const [timeframe, setTimeframe] = useState<ChartTimeframe>('W');
  const [range, setRange] = useState<ChartRange>('5Y');
  const [overlayMetric, setOverlayMetric] = useState<OverlayMetric | null>(null);
  const [overlayFrequency, setOverlayFrequency] = useState<FinancialFrequency>('quarterly');
  const [alertPlacementActive, setAlertPlacementActive] = useState(false);
  const [pickedAlertPrice, setPickedAlertPrice] = useState<number | null>(null);
  const [showInsiderTransactions, setShowInsiderTransactions] = useState(false);
  const [insiderLookback, setInsiderLookback] = useState<InsiderLookback>('chart');
  const [insiderDisplayMode, setInsiderDisplayMode] = useState<InsiderDisplayMode>('clusters');
  const [logScale, setLogScale] = useState(() => {
    try { return localStorage.getItem('mm-log-scale') === '1'; } catch { return false; }
  });
  const [watchBusy, setWatchBusy] = useState(false);
  const [comparisonExpressions, setComparisonExpressions] = useState(() => comparisonStateFromSearch(window.location.search).expressions);
  const [comparisonMode, setComparisonMode] = useState(() => comparisonStateFromSearch(window.location.search).active);
  const priceAlerts = usePriceAlerts(symbol);
  const overlayMetrics = useFinancialMetrics();
  const overlayIsValuation = isValuationMetric(overlayMetrics, overlayMetric);
  const overlayFrequencyChoices = metricInfo(overlayMetrics, overlayMetric)?.frequencies;
  const effectiveOverlayFrequency: FinancialFrequency = overlayIsValuation
    ? 'ttm'
    : overlayFrequencyChoices && !overlayFrequencyChoices.includes(overlayFrequency)
      ? overlayFrequencyChoices[0]
      : overlayFrequency;
  const overlaySeries = useFinancialSeries(symbol, overlayMetric ?? 'revenue', effectiveOverlayFrequency, overlayMetric != null);
  const comparisons = useChartComparisons(comparisonExpressions, timeframe);

  const detail = ticker.detail;
  const rawBars = detail ? timeframe === 'D' ? detail.series.daily : timeframe === 'M' ? detail.series.monthly : detail.series.weekly : [];
  const bars = useMemo(() => visibleBars(rawBars, range), [rawBars, range]);
  const comparisonLines = useMemo(
    () => buildComparisonLines(detail?.symbol ?? symbol.toUpperCase(), bars, comparisonExpressions, comparisons.payload?.series ?? []),
    [bars, comparisonExpressions, comparisons.payload?.series, detail?.symbol, symbol],
  );
  const overlayPoints = useMemo(() => {
    if (!overlayMetric || !overlaySeries.data || bars.length === 0) return undefined;
    const raw = isValuationPayload(overlaySeries.data)
      ? overlaySeries.data.observations.map((item) => ({ t: Math.floor(Date.parse(`${item.timestamp}T00:00:00Z`) / 1000), value: item.value != null && Number.isFinite(item.value) ? item.value : null }))
      : overlaySeries.data.observations.filter((item) => item.availableAt && Number.isFinite(item.value)).map((item) => ({ t: observationTime(item), value: item.value }));
    return snapOverlayToCandles(raw, bars.map((bar) => bar.t));
  }, [bars, overlayMetric, overlaySeries.data]);

  useEffect(() => {
    const search = comparisonSearch(comparisonExpressions, comparisonMode);
    window.history.replaceState({}, '', `${window.location.pathname}${search}`);
  }, [comparisonExpressions, comparisonMode]);

  if (ticker.loading || !detail) {
    return <TickerLoadState symbol={symbol} error={ticker.error} onClose={onClose} onRetry={ticker.reload} />;
  }

  const isWatched = watchlist.symbols.has(detail.symbol);
  const toggleWatch = async () => {
    setWatchBusy(true);
    try {
      if (isWatched) await watchlist.remove(detail.symbol);
      else await watchlist.add(detail.symbol, detail.name);
    } finally {
      setWatchBusy(false);
    }
  };
  const change = detail.quote.changePct;
  const quoteTone = change == null || change === 0 ? 'flat' : change > 0 ? 'up' : 'down';
  const chartEvents = sec.payload?.events ?? detail.events;
  const evidence = sec.payload?.evidence?.length ? sec.payload.evidence : detail.evidence;
  const chartEvidence = (() => {
    const latest = bars[bars.length - 1]?.t;
    const lookbackDays = insiderLookback === '90D' ? 90 : insiderLookback === '1Y' ? 366 : insiderLookback === '3Y' ? 3 * 366 : insiderLookback === '5Y' ? 5 * 366 : null;
    return evidence.filter((item) => {
      if (item.type !== 'Insider') return true;
      if (!showInsiderTransactions) return false;
      if (insiderLookback === 'chart') return item.t == null || bars.length === 0 || item.t >= bars[0].t;
      if (lookbackDays == null || latest == null || item.t == null) return true;
      return item.t >= latest - lookbackDays * 86400;
    });
  })();
  const chartEventRows = chartEvents.filter((event) => {
    if (event.kind !== 'insider') return true;
    if (!showInsiderTransactions) return false;
    const latest = bars[bars.length - 1]?.t;
    const lookbackDays = insiderLookback === '90D' ? 90 : insiderLookback === '1Y' ? 366 : insiderLookback === '3Y' ? 3 * 366 : insiderLookback === '5Y' ? 5 * 366 : null;
    if (insiderLookback === 'chart') return bars.length === 0 || event.t >= bars[0].t;
    return lookbackDays == null || latest == null || event.t >= latest - lookbackDays * 86400;
  });
  const overlayUnit = !overlaySeries.data ? undefined : isValuationPayload(overlaySeries.data) ? 'ratio' : overlaySeries.data.observations[0]?.unit;
  const timeframeLabel = timeframe === 'D' ? 'Daily bars' : timeframe === 'M' ? 'Monthly bars' : 'Weekly bars';
  const latestVisibleBar = bars[bars.length - 1];
  const showingComparison = comparisonMode && comparisonExpressions.length > 0;
  const removeComparison = (expression: string) => {
    setComparisonExpressions((current) => {
      const next = current.filter((item) => item !== expression);
      if (!next.length) setComparisonMode(false);
      return next;
    });
  };

  return (
    <div className="market-ticker-detail ticker-workspace">
      <header className="ticker-workspace-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0, flexWrap: 'wrap' }}>
          <button type="button" onClick={onClose} className="ticker-back-button"><ArrowLeft size={14} /> Market cockpit</button>
          <div style={{ minWidth: 0 }}>
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 9, flexWrap: 'wrap' }}><h1 style={{ margin: 0, fontFamily: "'JetBrains Mono', monospace", fontSize: 25, color: MM.text }}>{detail.symbol}</h1><span style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: 21, color: MM.muted }}>{detail.name}</span></div>
            <div style={{ marginTop: 3, fontSize: 10, color: MM.dim }}>Latest daily bar · {formatBarDate(detail.quote.barTime)} · {detail.quote.priceBasis.replace('_', '-')}</div>
          </div>
          <button type="button" onClick={() => void toggleWatch()} disabled={watchBusy} className={isWatched ? 'ticker-watch-button is-active' : 'ticker-watch-button'}>{watchBusy ? 'Updating…' : isWatched ? '✓ Watching' : '+ Watchlist'}</button>
          <button type="button" onClick={() => setCommandPaletteOpen(true)} className="ticker-command-search" aria-label="Search ticker or company"><Search size={13} /><span>Ticker</span></button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
          <div style={{ textAlign: 'right' }}><div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 21, color: MM.text }}>{formatQuote(detail.quote.price)}</div><div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11.5, color: toneColor(quoteTone) }}>{change == null ? '—' : `${change > 0 ? '+' : ''}${change.toFixed(2)}%`} vs prior daily bar</div></div>
        </div>
      </header>

      <main className="ticker-workspace-main">
        <PanelCard title={`${showingComparison ? 'Indexed comparison' : 'Price'} · ${timeframeLabel} · ${range === 'MAX' ? 'Max history' : range}`} status={comparisons.error && showingComparison ? 'error' : bars.length ? 'live' : 'error'} headerLayout="chart-toolbar" right={
          <MarketChartToolbar
            timeframe={timeframe}
            onTimeframe={setTimeframe}
            range={range}
            onRange={setRange}
            alertControl={showingComparison ? null : <PriceAlertControl alerts={priceAlerts.alerts} currentPrice={detail.quote.price ?? 0} pickedPrice={pickedAlertPrice} placing={alertPlacementActive} loading={priceAlerts.loading} error={priceAlerts.error} onStartPlacing={() => setAlertPlacementActive(true)} onStopPlacing={() => { setAlertPlacementActive(false); setPickedAlertPrice(null); }} onCreate={async (direction, threshold) => { const created = await priceAlerts.create(direction, threshold, detail.quote.price ?? 0); if (created) setPickedAlertPrice(null); return created; }} onCancel={priceAlerts.cancel} />}
            financialControls={showingComparison ? null : <FinancialOverlayControls metrics={overlayMetrics} metric={overlayMetric} frequency={effectiveOverlayFrequency} loading={overlaySeries.loading} onMetric={setOverlayMetric} onFrequency={setOverlayFrequency} />}
            comparisonControl={<ChartComparisonControl active={showingComparison} expressions={comparisonExpressions} onActive={setComparisonMode} onAdd={(expression) => setComparisonExpressions((current) => [...current, expression])} onRemove={removeComparison} onClear={() => { setComparisonExpressions([]); setComparisonMode(false); }} />}
            evidenceControl={showingComparison ? null : <ChartEvidenceControl showInsiderTransactions={showInsiderTransactions} onShowInsiderTransactions={setShowInsiderTransactions} lookback={insiderLookback} onLookback={setInsiderLookback} displayMode={insiderDisplayMode} onDisplayMode={setInsiderDisplayMode} />}
            logScale={logScale}
            onLogScale={setLogScale}
          />
        }>
          {!showingComparison && latestVisibleBar && (
            <div aria-label="Latest visible bar" style={{ display: 'flex', gap: 13, flexWrap: 'wrap', paddingBottom: 8, color: MM.dim, fontFamily: "'JetBrains Mono', monospace", fontSize: 9.5 }}>
              <span>{formatBarDate(latestVisibleBar.t)}</span>
              <span>O <b style={{ color: MM.textSoft }}>{formatQuote(latestVisibleBar.o)}</b></span>
              <span>H <b style={{ color: MM.textSoft }}>{formatQuote(latestVisibleBar.h)}</b></span>
              <span>L <b style={{ color: MM.textSoft }}>{formatQuote(latestVisibleBar.l)}</b></span>
              <span>C <b style={{ color: MM.textSoft }}>{formatQuote(latestVisibleBar.c)}</b></span>
              <span>V <b style={{ color: MM.textSoft }}>{formatVolume(latestVisibleBar.v)}</b></span>
            </div>
          )}
          {showingComparison && <ComparisonLegend labels={[detail.symbol, ...comparisonExpressions.filter((item) => item !== detail.symbol)]} lines={comparisonLines} loading={comparisons.loading} error={comparisons.error} />}
          <CandleChart bars={bars} events={chartEventRows} evidence={chartEvidence} height={isMobile ? 430 : 590} financialOverlay={overlayPoints} financialOverlayKind={overlayMetric ?? undefined} financialOverlayUnit={overlayUnit} financialOverlayValuation={overlayIsValuation} financialOverlayInverted={overlaySeries.data != null && isValuationPayload(overlaySeries.data) && overlaySeries.data.inverted === true} priceAlerts={priceAlerts.alerts} draftAlertPrice={pickedAlertPrice} alertPlacementActive={alertPlacementActive} onAlertPriceSelected={(price) => { setPickedAlertPrice(price); setAlertPlacementActive(false); }} comparisonMode={showingComparison} comparisonLines={comparisonLines} insiderDisplayMode={insiderDisplayMode} logScale={logScale} />
          {!showingComparison && <FinancialOverlayStatus metrics={overlayMetrics} metric={overlayMetric} state={overlaySeries} />}
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginTop: 8, borderTop: `1px solid ${MM.border}`, paddingTop: 8, fontSize: 9.5, color: MM.dimmer }}><span>{showingComparison ? 'Every line is rebased to 0% at its first observation in the visible range.' : `8-K and Form 144 markers on · Form 4 ${showInsiderTransactions ? `on (${insiderDisplayMode})` : 'off'}`}</span><span>{bars.length.toLocaleString()} bars · split-adjusted traded price</span></div>
        </PanelCard>
        <TickerOverviewRail detail={detail} evidence={evidence} />
      </main>

      <TickerSignalPanel detail={detail} />
      <TickerEvidencePanel state={sec} />
      <TickerReadPanel symbol={detail.symbol} />
    </div>
  );
}

function ComparisonLegend({ labels, lines, loading, error }: { labels: string[]; lines: ReturnType<typeof buildComparisonLines>; loading: boolean; error: string | null }) {
  if (error) return <div role="alert" style={{ paddingBottom: 8, color: MM.down, fontSize: 11 }}>{error}</div>;
  const byLabel = new Map(lines.map((line) => [line.label, line]));
  return (
    <div aria-label="Comparison legend" style={{ display: 'flex', gap: 14, flexWrap: 'wrap', paddingBottom: 8, fontFamily: "'JetBrains Mono', monospace", fontSize: 10 }}>
      {labels.map((label) => {
        const line = byLabel.get(label);
        if (!line) return <span key={label} style={{ color: MM.dim }}><b>{label}</b> {loading ? 'loading…' : 'no overlapping history'}</span>;
        const value = line.data[line.data.length - 1]?.value;
        return <span key={line.id} style={{ color: line.color }}><b>{line.label}</b> {value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(1)}%`}</span>;
      })}
    </div>
  );
}

function TickerLoadState({ symbol, error, onClose, onRetry }: { symbol: string; error: string | null; onClose: () => void; onRetry: () => Promise<void> }) {
  return (
    <div className="market-ticker-detail" style={{ display: 'grid', minHeight: 440, placeItems: 'center' }}>
      <div style={{ width: 'min(480px, 100%)', border: `1px solid ${error ? 'rgba(217,109,95,.35)' : MM.border}`, borderRadius: 14, background: MM.panel, padding: 22, textAlign: 'center' }}>
        <div style={{ color: error ? MM.down : MM.accent, font: '650 10px Inter', letterSpacing: '.12em', textTransform: 'uppercase' }}>{error ? 'Asset unavailable' : 'Loading asset workspace'}</div>
        <h1 style={{ color: MM.text, margin: '12px 0 8px', fontFamily: "'JetBrains Mono', monospace" }}>{symbol.toUpperCase()}</h1>
        <p role={error ? 'alert' : undefined} style={{ color: MM.dim, fontSize: 12, lineHeight: 1.55 }}>{error ?? 'Loading price history, deterministic signals, portfolio context, and current evidence…'}</p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 15 }}><button type="button" onClick={onClose} className="ticker-back-button"><ArrowLeft size={14} /> Market cockpit</button>{error && <button type="button" onClick={() => void onRetry()} className="ticker-watch-button"><RefreshCw size={13} /> Retry</button>}</div>
      </div>
    </div>
  );
}
