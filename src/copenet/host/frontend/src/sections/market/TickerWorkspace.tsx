// The ticker workspace frame.
//
// One fixed frame, no page scroll. Left edge navigates between assets, the chart owns the
// canvas, research docks beneath it on snap presets. Everything the operator does happens
// inside this rectangle — which is the difference between an instrument and an article.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowLeft, RefreshCw } from 'lucide-react';
import { assetProfile } from './assetProfile';
import { buildRailEntries, stepRail } from './symbolRailModel';
import { ChartStage, type StagePlot } from './ChartStage';
import { ChartToolbar } from './ChartToolbar';
import { CompareMenu, EventsMenu, PlotsMenu, SettingsMenu } from './chartMenus';
import { MM } from './marketUi';
import { PriceAlertControl } from './PriceAlertControl';
import { ResearchDrawer } from './ResearchDrawer';
import { SymbolRail } from './SymbolRail';
import { SymbolJump } from './SymbolJump';
import { TabOverview } from './TabOverview';
import { TickerEvidencePanel } from './TickerEvidencePanel';
import { TickerFundamentalsPanel } from './TickerFundamentalsPanel';
import { TickerReadPanel } from './TickerReadPanel';
import { TickerAssetBar } from './TickerAssetBar';
import { buildComparisonLines } from './chartComparison';
import { CHART_RANGES, CHART_TIMEFRAMES, visibleBars, type ChartRange, type ChartTimeframe } from './chartRanges';
import { observationTime, snapOverlayToCandles } from './financialOverlay';
import { isValuationMetric, metricInfo, useFinancialMetrics } from './useFinancialMetrics';
import { useChartComparisons } from './useChartComparisons';
import { useFinancialSeries } from './useFinancialSeries';
import { usePriceAlerts } from './usePriceAlerts';
import { useTickerDetail, useTickerEvidence, type MarketWatchlistState } from './useMarketMonitorData';
import type { InsiderDisplayMode, InsiderLookback } from './chartRanges';
import { isValuationPayload, type FinancialFrequency } from './types';
import {
  loadLogScale,
  loadRailCollapsed,
  loadSnaps,
  loadTab,
  nextSnap,
  pushRecent,
  saveLogScale,
  saveRailCollapsed,
  saveSnaps,
  saveTab,
  type DrawerSnap,
  type ResearchTab,
} from './tickerWorkspaceState';
import './tickerWorkspace.css';

export function TickerWorkspace({
  symbol,
  onClose,
  onNavigate,
  watchlist,
}: {
  symbol: string;
  onClose: () => void;
  onNavigate: (symbol: string) => void;
  watchlist: MarketWatchlistState;
}) {
  const ticker = useTickerDetail(symbol);
  // THE asset every pane describes. While a new symbol loads, the frame keeps the previous
  // asset painted — so every dependent source has to stay on that asset too. Keying them to
  // the requested symbol instead drew the incoming issuer's Form 4 markers, alert lines and
  // fundamental overlay on the outgoing issuer's candles: a market tool quietly attributing
  // one company's insider selling to another's price.
  const viewSymbol = ticker.detail?.symbol ?? symbol.trim().toUpperCase();
  const sec = useTickerEvidence(viewSymbol);
  const priceAlerts = usePriceAlerts(viewSymbol);
  const overlayMetrics = useFinancialMetrics();

  // --- workspace-sticky: how this operator likes to look at any asset -------------------
  const [timeframe, setTimeframe] = useState<ChartTimeframe>('W');
  const [range, setRange] = useState<ChartRange>('5Y');
  const [logScale, setLogScale] = useState(loadLogScale);
  const [showVolume, setShowVolume] = useState(true);
  const [tab, setTab] = useState<ResearchTab>(loadTab);
  const [snaps, setSnaps] = useState(loadSnaps);
  const [railCollapsed, setRailCollapsed] = useState(loadRailCollapsed);

  // --- symbol-scoped: reset on switch, or a comparison silently follows you to the next
  //     asset and the URL is rewritten as if you had asked for it ------------------------
  const [overlayMetric, setOverlayMetric] = useState<string | null>(null);
  const [overlayFrequency, setOverlayFrequency] = useState<FinancialFrequency>('quarterly');
  const [comparisons, setComparisons] = useState<string[]>([]);
  const [showInsider, setShowInsider] = useState(false);
  const [insiderLookback, setInsiderLookback] = useState<InsiderLookback>('chart');
  const [insiderDisplay, setInsiderDisplay] = useState<InsiderDisplayMode>('clusters');
  const [alertPlacing, setAlertPlacing] = useState(false);
  const [pickedAlertPrice, setPickedAlertPrice] = useState<number | null>(null);

  const [recents, setRecents] = useState<string[]>([]);
  const [railCursor, setRailCursor] = useState<string | null>(null);
  const [jumpOpen, setJumpOpen] = useState(false);
  const [jumpSeed, setJumpSeed] = useState('');
  const [watchBusy, setWatchBusy] = useState(false);

  const normalized = symbol.trim().toUpperCase();

  useEffect(() => {
    setOverlayMetric(null);
    setComparisons([]);
    setPickedAlertPrice(null);
    setAlertPlacing(false);
    setRailCursor(null);
  }, [normalized]);

  useEffect(() => {
    setRecents((current) => pushRecent(normalized, current));
  }, [normalized]);

  useEffect(() => saveTab(tab), [tab]);
  useEffect(() => saveSnaps(snaps), [snaps]);
  useEffect(() => saveLogScale(logScale), [logScale]);
  useEffect(() => saveRailCollapsed(railCollapsed), [railCollapsed]);

  const detail = ticker.detail;
  const profile = assetProfile(detail);

  // A fund has no Fundamentals or Evidence tab. Without this, a persisted `fundamentals`
  // rendered its panel — and fired an SEC fetch — with no tab highlighted anywhere.
  useEffect(() => {
    if (!profile.tabs.includes(tab)) setTab(profile.tabs[0]);
  }, [profile.tabs, tab]);

  const snap = snaps[tab] ?? 'half';
  const setSnap = useCallback((next: DrawerSnap) => setSnaps((current) => ({ ...current, [tab]: next })), [tab]);

  // Comparison rebases the price pane to indexed %, so every price-anchored plot — alerts,
  // fundamentals, filing markers — is genuinely inapplicable while it is on. The controls
  // stay visible and disabled with that reason rather than disappearing.
  const comparing = comparisons.length > 0;

  const overlayIsValuation = isValuationMetric(overlayMetrics, overlayMetric);
  const overlayChoices = metricInfo(overlayMetrics, overlayMetric)?.frequencies;
  const effectiveFrequency: FinancialFrequency = overlayIsValuation
    ? 'ttm'
    : overlayChoices && !overlayChoices.includes(overlayFrequency)
      ? overlayChoices[0]
      : overlayFrequency;
  const overlaySeries = useFinancialSeries(viewSymbol, overlayMetric ?? 'revenue', effectiveFrequency, overlayMetric != null);
  const comparisonData = useChartComparisons(comparisons, timeframe);

  const rawBars = detail ? (timeframe === 'D' ? detail.series.daily : timeframe === 'M' ? detail.series.monthly : detail.series.weekly) : [];
  const bars = useMemo(() => visibleBars(rawBars, range), [rawBars, range]);

  const comparisonLines = useMemo(
    () => buildComparisonLines(detail?.symbol ?? normalized, bars, comparisons, comparisonData.payload?.series ?? []),
    [bars, comparisons, comparisonData.payload?.series, detail?.symbol, normalized],
  );

  const overlayPoints = useMemo(() => {
    if (!overlayMetric || !overlaySeries.data || bars.length === 0) return undefined;
    const raw = isValuationPayload(overlaySeries.data)
      ? overlaySeries.data.observations.map((item) => ({
          t: Math.floor(Date.parse(`${item.timestamp}T00:00:00Z`) / 1000),
          value: item.value != null && Number.isFinite(item.value) ? item.value : null,
        }))
      : overlaySeries.data.observations
          .filter((item) => item.availableAt && Number.isFinite(item.value))
          .map((item) => ({ t: observationTime(item), value: item.value }));
    return snapOverlayToCandles(raw, bars.map((bar) => bar.t));
  }, [bars, overlayMetric, overlaySeries.data]);

  const railEntries = useMemo(
    () => buildRailEntries({ watchlist: watchlist.items, recents, peers: comparisons, current: normalized }),
    [watchlist.items, recents, comparisons, normalized],
  );

  const evidence = sec.payload?.evidence?.length ? sec.payload.evidence : detail?.evidence ?? [];
  const chartEvents = sec.payload?.events ?? detail?.events ?? [];

  const lookbackDays = insiderLookback === '90D' ? 90 : insiderLookback === '1Y' ? 366 : insiderLookback === '3Y' ? 3 * 366 : insiderLookback === '5Y' ? 5 * 366 : null;
  const latestBarTime = bars[bars.length - 1]?.t;
  const chartEvidence = evidence.filter((item) => {
    if (item.type !== 'Insider') return true;
    if (!showInsider) return false;
    if (insiderLookback === 'chart') return item.t == null || bars.length === 0 || item.t >= bars[0].t;
    if (lookbackDays == null || latestBarTime == null || item.t == null) return true;
    return item.t >= latestBarTime - lookbackDays * 86400;
  });
  const chartEventRows = chartEvents.filter((event) => {
    if (event.kind !== 'insider') return true;
    if (!showInsider) return false;
    if (insiderLookback === 'chart') return bars.length === 0 || event.t >= bars[0].t;
    return lookbackDays == null || latestBarTime == null || event.t >= latestBarTime - lookbackDays * 86400;
  });

  const openTab = useCallback((next: ResearchTab) => {
    setTab(next);
    setSnaps((current) => ({ ...current, [next]: current[next] === 'collapsed' ? 'half' : current[next] }));
  }, []);

  const plotMetric = useCallback((metric: string) => {
    setOverlayMetric((current) => (current === metric ? null : metric));
  }, []);

  const addComparison = useCallback((expression: string) => {
    setComparisons((current) => (current.includes(expression) || current.length >= 5 ? current : [...current, expression]));
  }, []);

  // ------------------------------------------------------------------ keyboard
  const jumpOpenRef = useRef(jumpOpen);
  jumpOpenRef.current = jumpOpen;

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      // A focused control owns its own keys: Enter activates a button, a letter jumps a
      // <select>'s options. Only INPUT/TEXTAREA/contentEditable were excluded before, so
      // after any j/k the drawer's own buttons stopped responding to Enter.
      const owned = Boolean(
        target
          && (target.tagName === 'INPUT'
            || target.tagName === 'TEXTAREA'
            || target.tagName === 'SELECT'
            || target.tagName === 'BUTTON'
            || target.tagName === 'A'
            || target.isContentEditable
            || target.closest('[role="dialog"]')),
      );
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      if (owned || jumpOpenRef.current) return;

      const key = event.key;
      if (key === 'Escape') return;

      // Interval and range are pure client-side filters over bars already in memory, so
      // there is no excuse for them being pointer-only.
      if (key === 'd' || key === 'w' || key === 'm') {
        const value = key.toUpperCase() as ChartTimeframe;
        if (CHART_TIMEFRAMES.includes(value)) { setTimeframe(value); event.preventDefault(); }
        return;
      }
      if (key >= '1' && key <= '5') { setRange(CHART_RANGES[Number(key) - 1]); event.preventDefault(); return; }
      if (key === '0') { setRange('MAX'); event.preventDefault(); return; }
      if (key === 'l') { setLogScale((value) => !value); event.preventDefault(); return; }
      if (key === '\\') { setSnaps((current) => ({ ...current, [tab]: nextSnap(current[tab] ?? 'half') })); event.preventDefault(); return; }
      if (key === 'j' || key === 'k') {
        const from = railCursor ?? normalized;
        const next = stepRail(railEntries, from, key === 'j' ? 1 : -1);
        if (next) { setRailCursor(next); event.preventDefault(); }
        return;
      }
      if (key === 'Enter' && railCursor && railCursor !== normalized) {
        onNavigate(railCursor);
        event.preventDefault();
        return;
      }
      // Symbol entry is `/`, never a bare letter. Bare-type-to-switch is the nicer reflex
      // right up until you type DIS, WMT or LLY and silently get a different interval
      // instead of a different asset — a wrong action that gives no feedback is worse than
      // one extra keystroke, so the letters belong to the chart and `/` opens the symbol.
      if (key === '/') {
        setJumpSeed('');
        setJumpOpen(true);
        event.preventDefault();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [normalized, onNavigate, railCursor, railEntries, tab]);

  if (!detail) {
    return <TickerLoadState symbol={normalized} error={ticker.error} onClose={onClose} onRetry={ticker.reload} />;
  }

  const watched = watchlist.symbols.has(detail.symbol);
  const toggleWatch = async () => {
    setWatchBusy(true);
    try {
      if (watched) await watchlist.remove(detail.symbol);
      else await watchlist.add(detail.symbol, detail.name);
    } finally {
      setWatchBusy(false);
    }
  };

  const overlayInfo = overlayMetric ? overlayMetrics.find((entry) => entry.id === overlayMetric) ?? null : null;
  const overlayLatest = overlaySeries.data?.observations?.filter((row) => row.value != null).slice(-1)[0];
  const plots: StagePlot[] = [];
  if (overlayInfo && overlayPoints?.length) {
    plots.push({
      id: overlayInfo.id,
      label: overlayInfo.label,
      color: MM.info,
      value: overlayLatest?.value == null
        ? undefined
        : overlayIsValuation
          ? `${overlayLatest.value.toFixed(1)}×`
          : undefined,
      onRemove: () => setOverlayMetric(null),
    });
  }

  const secWarnings = (sec.payload?.warnings?.length ?? 0) + (sec.error ? 1 : 0);
  const overlayWarnings = overlaySeries.error ? 1 : 0;
  const dataWarning = detail.intelligence?.dataQuality.thinHistory
    ? `Thin history — ${detail.intelligence.dataQuality.historyWeeks} weeks. Trend conclusions are lower confidence.`
    : null;

  return (
    <div className="tw">
      <TickerAssetBar
        detail={detail}
        profile={profile}
        watched={watched}
        watchBusy={watchBusy}
        pending={ticker.stale ? symbol.trim().toUpperCase() : null}
        onBack={onClose}
        onToggleWatch={() => void toggleWatch()}
        onOpenPosition={() => openTab('overview')}
        onOpenJump={() => { setJumpSeed(''); setJumpOpen(true); }}
      />

      <div className="tw-body">
        <SymbolRail
          entries={railEntries}
          current={detail.symbol}
          cursor={railCursor}
          collapsed={railCollapsed}
          onToggle={() => setRailCollapsed((value) => !value)}
          onSelect={onNavigate}
        />

        <div className="tw-main">
          <ChartToolbar
            timeframe={timeframe}
            onTimeframe={setTimeframe}
            range={range}
            onRange={setRange}
            logScale={logScale}
            onLogScale={setLogScale}
            comparisonActive={comparing}
            comparisonCount={comparisons.length}
            plotCount={plots.length}
            eventsActive={showInsider}
            drawerOpen={snap !== 'collapsed'}
            onToggleDrawer={() => setSnap(snap === 'collapsed' ? 'half' : 'collapsed')}
            plotsMenu={(anchor, open, close) => (
              <PlotsMenu
                anchor={anchor}
                open={open}
                onClose={close}
                metrics={overlayMetrics}
                metric={overlayMetric}
                frequency={effectiveFrequency}
                onFrequency={setOverlayFrequency}
                onClearMetric={() => setOverlayMetric(null)}
                showVolume={showVolume}
                onShowVolume={setShowVolume}
                comparisonActive={comparing}
                onBrowse={() => openTab('fundamentals')}
              />
            )}
            compareMenu={(anchor, open, close) => (
              <CompareMenu
                anchor={anchor}
                open={open}
                onClose={close}
                expressions={comparisons}
                onAdd={addComparison}
                onRemove={(expression) => setComparisons((current) => current.filter((item) => item !== expression))}
                onClear={() => setComparisons([])}
              />
            )}
            eventsMenu={(anchor, open, close) => (
              <EventsMenu
                anchor={anchor}
                open={open}
                onClose={close}
                showInsider={showInsider}
                onShowInsider={setShowInsider}
                lookback={insiderLookback}
                onLookback={setInsiderLookback}
                displayMode={insiderDisplay}
                onDisplayMode={setInsiderDisplay}
                disabled={comparing}
              />
            )}
            alertControl={
              <PriceAlertControl
                alerts={priceAlerts.alerts}
                currentPrice={detail.quote.price ?? 0}
                pickedPrice={pickedAlertPrice}
                placing={alertPlacing}
                loading={priceAlerts.loading}
                error={priceAlerts.error}
                disabled={comparing}
                onStartPlacing={() => setAlertPlacing(true)}
                onStopPlacing={() => { setAlertPlacing(false); setPickedAlertPrice(null); }}
                onCreate={async (direction, threshold) => {
                  const created = await priceAlerts.create(direction, threshold, detail.quote.price ?? 0);
                  if (created) setPickedAlertPrice(null);
                  return created;
                }}
                onCancel={priceAlerts.cancel}
              />
            }
            settingsMenu={(anchor, open, close) => (
              <SettingsMenu
                anchor={anchor}
                open={open}
                onClose={close}
                logScale={logScale}
                onLogScale={setLogScale}
                intelligence={detail.intelligence}
                priceBasis={detail.quote.priceBasis}
                barCount={bars.length}
                plotSource={
                  overlayInfo && overlaySeries.data
                    ? {
                        label: overlayInfo.label,
                        count: overlaySeries.data.observations.length,
                        form: overlayLatest?.sources?.[0]?.form,
                        accession: overlayLatest?.sources?.[0]?.accessionNumber,
                        url: overlayLatest?.sources?.[0]?.sourceUrl,
                        warnings: overlaySeries.data.warnings ?? [],
                      }
                    : null
                }
              />
            )}
          />

          <ChartStage
            symbol={detail.symbol}
            timeframe={timeframe}
            bars={bars}
            events={chartEventRows}
            evidence={chartEvidence}
            plots={plots}
            warning={dataWarning}
            comparisonMode={comparing}
            comparisonLines={comparisonLines}
            comparisonError={comparing ? comparisonData.error : null}
            financialOverlay={comparing ? undefined : overlayPoints}
            financialOverlayKind={overlayMetric ?? undefined}
            financialOverlayUnit={
              !overlaySeries.data ? undefined : isValuationPayload(overlaySeries.data) ? 'ratio' : overlaySeries.data.observations[0]?.unit
            }
            financialOverlayValuation={overlayIsValuation}
            financialOverlayInverted={overlaySeries.data != null && isValuationPayload(overlaySeries.data) && overlaySeries.data.inverted === true}
            priceAlerts={comparing ? [] : priceAlerts.alerts}
            draftAlertPrice={pickedAlertPrice}
            alertPlacementActive={alertPlacing}
            onAlertPriceSelected={(price) => { setPickedAlertPrice(price); setAlertPlacing(false); }}
            insiderDisplayMode={insiderDisplay}
            logScale={logScale}
            showVolume={showVolume}
            layoutKey={`${snap}:${railCollapsed}`}
            overlay={
              jumpOpen ? (
                <SymbolJump
                  seed={jumpSeed}
                  onClose={() => setJumpOpen(false)}
                  onPick={(picked) => { setJumpOpen(false); onNavigate(picked); }}
                />
              ) : null
            }
          />

          <ResearchDrawer
            tab={tab}
            onTab={setTab}
            tabs={profile.tabs}
            snap={snap}
            onSnap={setSnap}
            warnings={{ evidence: secWarnings, fundamentals: overlayWarnings }}
          >
            {/* Each panel receives `active`, which is how Codex's panels gate their own
                fetching and lazily import Recharts — the drawer's tab state drives it for
                free, so nothing below the chart loads until you open it. */}
            {tab === 'overview' && <TabOverview detail={detail} profile={profile} />}
            {tab === 'fundamentals' && <TickerFundamentalsPanel symbol={detail.symbol} active={tab === 'fundamentals'} />}
            {tab === 'evidence' && <TickerEvidencePanel state={sec} active={tab === 'evidence'} />}
            {tab === 'synthesis' && <TickerReadPanel symbol={detail.symbol} />}
          </ResearchDrawer>
        </div>
      </div>
    </div>
  );
}

function TickerLoadState({ symbol, error, onClose, onRetry }: { symbol: string; error: string | null; onClose: () => void; onRetry: () => Promise<void> }) {
  return (
    <div className="tw" style={{ display: 'grid', placeItems: 'center' }}>
      <div style={{ width: 'min(440px, 100%)', border: `1px solid ${error ? 'rgba(217,109,95,.3)' : MM.border}`, borderRadius: 6, background: MM.panel, padding: 22, textAlign: 'center' }}>
        <div style={{ color: error ? MM.down : MM.accent, font: '650 9px Inter', letterSpacing: '.13em', textTransform: 'uppercase' }}>
          {error ? 'Asset unavailable' : 'Loading workspace'}
        </div>
        <h1 style={{ color: MM.text, margin: '11px 0 8px', fontFamily: "'JetBrains Mono', monospace", fontSize: 22 }}>{symbol}</h1>
        <p role={error ? 'alert' : undefined} style={{ color: MM.dim, fontSize: 11, lineHeight: 1.55 }}>
          {error ?? 'Loading price history, deterministic signals, and current evidence…'}
        </p>
        <div style={{ display: 'flex', justifyContent: 'center', gap: 8, marginTop: 15 }}>
          <button type="button" className="tw-btn" onClick={onClose}><ArrowLeft size={13} /> Market cockpit</button>
          {error && <button type="button" className="tw-btn" onClick={() => void onRetry()}><RefreshCw size={12} /> Retry</button>}
        </div>
      </div>
    </div>
  );
}
