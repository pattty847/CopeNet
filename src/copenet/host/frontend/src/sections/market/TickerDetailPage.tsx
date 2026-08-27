import { useMemo, useState } from 'react';
import { ArrowLeft, RefreshCw } from 'lucide-react';
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
import { TickerSearch } from './TickerSearch';
import { TickerSignalPanel } from './TickerSignalPanel';
import { PriceAlertControl } from './PriceAlertControl';
import { useTickerDetail, useTickerEvidence, type MarketWatchlistState } from './useMarketMonitorData';
import { useIsMobile } from '../../lib/responsive';

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

export function TickerDetailPage({ symbol, onClose, onOpenTicker, watchlist }: { symbol: string; onClose: () => void; onOpenTicker: (symbol: string) => void; watchlist: MarketWatchlistState }) {
  const ticker = useTickerDetail(symbol);
  const sec = useTickerEvidence(symbol);
  const isMobile = useIsMobile();
  const [timeframe, setTimeframe] = useState<ChartTimeframe>('W');
  const [range, setRange] = useState<ChartRange>('5Y');
  const [overlayMetric, setOverlayMetric] = useState<OverlayMetric | null>(null);
  const [overlayFrequency, setOverlayFrequency] = useState<FinancialFrequency>('quarterly');
  const [alertPlacementActive, setAlertPlacementActive] = useState(false);
  const [pickedAlertPrice, setPickedAlertPrice] = useState<number | null>(null);
  const [watchBusy, setWatchBusy] = useState(false);
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

  const detail = ticker.detail;
  const rawBars = detail ? timeframe === 'D' ? detail.series.daily : timeframe === 'M' ? detail.series.monthly : detail.series.weekly : [];
  const bars = useMemo(() => visibleBars(rawBars, range), [rawBars, range]);
  const overlayPoints = useMemo(() => {
    if (!overlayMetric || !overlaySeries.data || bars.length === 0) return undefined;
    const raw = isValuationPayload(overlaySeries.data)
      ? overlaySeries.data.observations.map((item) => ({ t: Math.floor(Date.parse(`${item.timestamp}T00:00:00Z`) / 1000), value: item.value != null && Number.isFinite(item.value) ? item.value : null }))
      : overlaySeries.data.observations.filter((item) => item.availableAt && Number.isFinite(item.value)).map((item) => ({ t: observationTime(item), value: item.value }));
    return snapOverlayToCandles(raw, bars.map((bar) => bar.t));
  }, [bars, overlayMetric, overlaySeries.data]);

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
  const overlayUnit = !overlaySeries.data ? undefined : isValuationPayload(overlaySeries.data) ? 'ratio' : overlaySeries.data.observations[0]?.unit;
  const timeframeLabel = timeframe === 'D' ? 'Daily bars' : timeframe === 'M' ? 'Monthly bars' : 'Weekly bars';
  const latestVisibleBar = bars[bars.length - 1];

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
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 10, flexWrap: 'wrap' }}>
          {!isMobile && <TickerSearch onSelect={(next) => onOpenTicker(next)} />}
          <div style={{ textAlign: 'right' }}><div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 21, color: MM.text }}>{formatQuote(detail.quote.price)}</div><div style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11.5, color: toneColor(quoteTone) }}>{change == null ? '—' : `${change > 0 ? '+' : ''}${change.toFixed(2)}%`} vs prior daily bar</div></div>
        </div>
      </header>

      {isMobile && <TickerSearch onSelect={(next) => onOpenTicker(next)} fullWidth />}

      <main className="ticker-workspace-main">
        <PanelCard title={`Price · ${timeframeLabel} · ${range === 'MAX' ? 'Max history' : range}`} status={bars.length ? 'live' : 'error'} headerLayout="mobile-toolbar" right={
          <MarketChartToolbar
            timeframe={timeframe}
            onTimeframe={setTimeframe}
            range={range}
            onRange={setRange}
            alertControl={<PriceAlertControl alerts={priceAlerts.alerts} currentPrice={detail.quote.price ?? 0} pickedPrice={pickedAlertPrice} placing={alertPlacementActive} loading={priceAlerts.loading} error={priceAlerts.error} onStartPlacing={() => setAlertPlacementActive(true)} onStopPlacing={() => setAlertPlacementActive(false)} onCreate={(direction, threshold) => priceAlerts.create(direction, threshold, detail.quote.price ?? 0)} onCancel={priceAlerts.cancel} />}
            financialControls={<FinancialOverlayControls metrics={overlayMetrics} metric={overlayMetric} frequency={effectiveOverlayFrequency} loading={overlaySeries.loading} onMetric={setOverlayMetric} onFrequency={setOverlayFrequency} />}
          />
        }>
          {latestVisibleBar && (
            <div aria-label="Latest visible bar" style={{ display: 'flex', gap: 13, flexWrap: 'wrap', paddingBottom: 8, color: MM.dim, fontFamily: "'JetBrains Mono', monospace", fontSize: 9.5 }}>
              <span>{formatBarDate(latestVisibleBar.t)}</span>
              <span>O <b style={{ color: MM.textSoft }}>{formatQuote(latestVisibleBar.o)}</b></span>
              <span>H <b style={{ color: MM.textSoft }}>{formatQuote(latestVisibleBar.h)}</b></span>
              <span>L <b style={{ color: MM.textSoft }}>{formatQuote(latestVisibleBar.l)}</b></span>
              <span>C <b style={{ color: MM.textSoft }}>{formatQuote(latestVisibleBar.c)}</b></span>
              <span>V <b style={{ color: MM.textSoft }}>{formatVolume(latestVisibleBar.v)}</b></span>
            </div>
          )}
          <CandleChart bars={bars} events={chartEvents} evidence={evidence} height={isMobile ? 430 : 590} financialOverlay={overlayPoints} financialOverlayKind={overlayMetric ?? undefined} financialOverlayUnit={overlayUnit} financialOverlayValuation={overlayIsValuation} financialOverlayInverted={overlaySeries.data != null && isValuationPayload(overlaySeries.data) && overlaySeries.data.inverted === true} priceAlerts={priceAlerts.alerts} alertPlacementActive={alertPlacementActive} onAlertPriceSelected={(price) => { setPickedAlertPrice(price); setAlertPlacementActive(false); }} />
          <FinancialOverlayStatus metrics={overlayMetrics} metric={overlayMetric} state={overlaySeries} />
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, flexWrap: 'wrap', marginTop: 8, borderTop: `1px solid ${MM.border}`, paddingTop: 8, fontSize: 9.5, color: MM.dimmer }}><span>SEC markers and active alerts remain synchronized to the visible bars.</span><span>{bars.length.toLocaleString()} bars · split-adjusted traded price · right-click price axis for log scale</span></div>
        </PanelCard>
        <TickerOverviewRail detail={detail} evidence={evidence} />
      </main>

      <TickerSignalPanel detail={detail} />
      <TickerEvidencePanel state={sec} />
      <TickerReadPanel symbol={detail.symbol} />
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
