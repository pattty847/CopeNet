import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { assetProfile } from './assetProfile';
import { buildRailEntries } from './symbolRailModel';
import { barsPerYear, createIndicatorComputer } from './indicators/compute';
import type { IndicatorRowActions } from './indicators/IndicatorRows';
import { addIndicator, applyPaneStretch, configureIndicator, duplicateIndicator, loadIndicatorLayout, moveIndicator, removeIndicator, resetIndicator, saveIndicatorLayout, setIndicatorVisibility, styleIndicator, type IndicatorInstance } from './indicators/state';
import { buildComparisonLines } from './chartComparison';
import { visibleBars, type ChartRange, type ChartTimeframe, type InsiderDisplayMode, type InsiderLookback } from './chartRanges';
import { observationTime, snapOverlayToCandles } from './financialOverlay';
import { isValuationMetric, metricInfo, useFinancialMetrics } from './useFinancialMetrics';
import { useChartComparisons } from './useChartComparisons';
import { useFinancialSeries } from './useFinancialSeries';
import { usePriceAlerts } from './usePriceAlerts';
import { replayCursorIndex } from './replay/chartReplay';
import { useChartReplay, useReplayTrailingTimes } from './replay/useChartReplay';
import { useTickerDrawerLayout } from './useTickerDrawerLayout';
import { useTickerDetail, useTickerEvidence, type MarketWatchlistState } from './useMarketMonitorData';
import { isValuationPayload, type FinancialFrequency } from './types';
import { loadLogScale, loadRailCollapsed, loadTab, pushRecent, saveLogScale, saveRailCollapsed, saveTab, type ResearchTab } from './tickerWorkspaceState';

/** One owner for the values rendered by the ticker and captured for agent turns. */
export function useTickerViewModel(symbol: string, watchlist: MarketWatchlistState) {
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
  // Workspace-sticky, like the interval and the pane set: an analyst configures their
  // instrument once and looks at every asset through it. The VALUES recompute per symbol.
  const [indicatorLayout, setIndicatorLayout] = useState(loadIndicatorLayout);
  const indicators = indicatorLayout.instances;
  // The instance list is what every transition operates on; the pane division rides along
  // beside it in the same persisted blob.
  const setIndicators = useCallback(
    (update: (current: IndicatorInstance[]) => IndicatorInstance[]) =>
      setIndicatorLayout((layout) => ({ ...layout, instances: update(layout.instances) })),
    [],
  );

  /** A pane separator has been dragged. Stored as stretch factors, which are relative, so a
   *  division saved on a laptop restores proportionally on a monitor. */
  const handlePaneStretch = useCallback(
    (next: { priceStretch: number; byInstance: Record<string, number> }) => {
      setIndicatorLayout((layout) => {
        const instances = applyPaneStretch(layout.instances, next.byInstance);
        const priceMoved = Math.abs(layout.priceStretch - next.priceStretch) >= 0.01;
        if (instances === layout.instances && !priceMoved) return layout;
        return { instances, priceStretch: priceMoved ? next.priceStretch : layout.priceStretch };
      });
    },
    [],
  );
  const drawer = useTickerDrawerLayout(tab);
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
  useEffect(() => saveIndicatorLayout(indicatorLayout), [indicatorLayout]);
  useEffect(() => saveLogScale(logScale), [logScale]);
  useEffect(() => saveRailCollapsed(railCollapsed), [railCollapsed]);

  const detail = ticker.detail;
  const profile = assetProfile(detail);

  // A fund has no Fundamentals or Evidence tab. Without this, a persisted `fundamentals`
  // rendered its panel — and fired an SEC fetch — with no tab highlighted anywhere.
  useEffect(() => {
    if (!profile.tabs.includes(tab)) setTab(profile.tabs[0]);
  }, [profile.tabs, tab]);

  const {
    snap,
    size: drawerSize,
    setSnap,
    resize: resizeDrawer,
    ensureOpen: ensureDrawerOpen,
    cycleSnap: cycleDrawerSnap,
  } = drawer;

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
  const fullBars = useMemo(() => visibleBars(rawBars, range), [rawBars, range]);

  // REPLAY IS A TRUNCATION, AND IT HAPPENS ONCE, HERE.
  //
  // Every series the chart draws is derived below from `bars` — indicators, the financial
  // overlay, comparisons, filing markers. Cutting the bars at the cursor therefore cuts all
  // of them, and there is no second place where a future value could survive the cut. Doing
  // it per-consumer instead is how a replay leaks: one overlooked derivation draws tomorrow's
  // earnings marker on a chart the operator believes stops at last Tuesday.
  const replay = useChartReplay(fullBars);
  const bars = useMemo(
    () => (replay.active ? fullBars.slice(0, replay.index + 1) : fullBars),
    [fullBars, replay.active, replay.index],
  );
  const replayTime = replay.active ? bars[bars.length - 1]?.t ?? null : null;
  const replayTrailingTimes = useReplayTrailingTimes(fullBars, replay);

  // A replay is an argument about ONE asset's history. Carrying the cursor across a symbol
  // switch would land it on an unrelated date and keep the transport armed over a chart the
  // operator never put into replay.
  const exitReplay = replay.exit;
  useEffect(() => { exitReplay(); }, [normalized, exitReplay]);

  // Indicators compute over the FULL history and are sliced to the visible range afterwards,
  // so changing 6M/1Y/5Y re-cuts one calculation instead of restarting every warm-up. The
  // computer memoises per configuration, so an unrelated re-render costs nothing.
  //
  // Under replay the history itself is cut at the cursor rather than the outputs being
  // filtered afterwards: the visible window has to stay a SUFFIX of what was computed, which
  // is the alignment rule `compute` relies on. Because every calculation is causal, the
  // retained values are bit-identical to the untruncated ones — the cut costs a recompute
  // per step and buys an indicator that genuinely never saw the future.
  const indicatorHistory = useMemo(
    () => (replayTime == null ? rawBars : rawBars.slice(0, replayCursorIndex(rawBars, replayTime) + 1)),
    [rawBars, replayTime],
  );
  const indicatorComputer = useRef(createIndicatorComputer());
  const computedIndicators = useMemo(
    () => indicatorComputer.current.compute(indicatorHistory, bars.length, indicators, { barsPerYear: barsPerYear(timeframe) }),
    [indicatorHistory, bars.length, indicators, timeframe],
  );

  const comparisonLines = useMemo(
    () => buildComparisonLines(detail?.symbol ?? normalized, bars, comparisons, comparisonData.payload?.formulas ?? []),
    [bars, comparisons, comparisonData.payload?.formulas, detail?.symbol, normalized],
  );
  const comparisonWarning = comparisonData.error
    ?? comparisonData.payload?.formulas.flatMap((formula) => formula.warnings)[0]
    ?? null;

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
  // Viewport publication rerenders this owner. Preserve these inputs so a pan/zoom
  // does not trigger CandleChart data replacement and fitContent again.
  const chartEvidence = useMemo(() => evidence.filter((item) => {
    // Undated evidence cannot be shown to be in the past, so replay drops it rather than
    // drawing something that might belong to a day the operator has not reached yet.
    if (replayTime != null && (item.t == null || item.t > replayTime)) return false;
    if (item.type !== 'Insider') return true;
    if (!showInsider) return false;
    if (insiderLookback === 'chart') return item.t == null || bars.length === 0 || item.t >= bars[0].t;
    if (lookbackDays == null || latestBarTime == null || item.t == null) return true;
    return item.t >= latestBarTime - lookbackDays * 86400;
  }), [evidence, showInsider, insiderLookback, bars, lookbackDays, latestBarTime, replayTime]);
  const chartEventRows = useMemo(() => chartEvents.filter((event) => {
    if (replayTime != null && event.t > replayTime) return false;
    if (event.kind !== 'insider') return true;
    if (!showInsider) return false;
    if (insiderLookback === 'chart') return bars.length === 0 || event.t >= bars[0].t;
    return lookbackDays == null || latestBarTime == null || event.t >= latestBarTime - lookbackDays * 86400;
  }), [chartEvents, showInsider, insiderLookback, bars, lookbackDays, latestBarTime, replayTime]);

  const openTab = useCallback((next: ResearchTab) => {
    setTab(next);
    ensureDrawerOpen(next);
  }, [ensureDrawerOpen]);

  const plotMetric = useCallback((metric: string) => {
    setOverlayMetric((current) => (current === metric ? null : metric));
  }, []);

  const indicatorActions = useMemo<IndicatorRowActions>(() => ({
    onConfigure: (instanceId, patch) => setIndicators((current) => configureIndicator(current, instanceId, patch)),
    onStyle: (instanceId, outputKey, style) => setIndicators((current) => styleIndicator(current, instanceId, outputKey, style)),
    onVisibility: (instanceId, visible) => setIndicators((current) => setIndicatorVisibility(current, instanceId, visible)),
    onDuplicate: (instanceId) => setIndicators((current) => duplicateIndicator(current, instanceId)),
    onReset: (instanceId) => setIndicators((current) => resetIndicator(current, instanceId)),
    onRemove: (instanceId) => setIndicators((current) => removeIndicator(current, instanceId)),
    onMove: (instanceId, delta) => setIndicators((current) => moveIndicator(current, instanceId, delta)),
  }), []);

  const addIndicatorToLayout = useCallback((indicatorId: string) => {
    setIndicators((current) => addIndicator(current, indicatorId));
  }, []);

  const addComparison = useCallback((expression: string) => {
    setComparisons((current) => (current.includes(expression) || current.length >= 5 ? current : [...current, expression]));
  }, []);

  return {
    ticker, viewSymbol, sec, priceAlerts, overlayMetrics, timeframe,
    setTimeframe, range, setRange, logScale, setLogScale, showVolume,
    setShowVolume, tab, indicators, indicatorLayout, handlePaneStretch, railCollapsed,
    setRailCollapsed, overlayMetric, setOverlayMetric, effectiveFrequency, setOverlayFrequency, comparisons,
    setComparisons, showInsider, setShowInsider, insiderLookback, setInsiderLookback, insiderDisplay,
    setInsiderDisplay, alertPlacing, setAlertPlacing, pickedAlertPrice, setPickedAlertPrice, railCursor,
    setRailCursor, jumpOpen, setJumpOpen, jumpSeed, setJumpSeed, watchBusy,
    setWatchBusy, normalized, detail, profile, snap, drawerSize,
    setSnap, resizeDrawer, cycleDrawerSnap, comparing, overlaySeries, overlayIsValuation,
    rawBars, fullBars, bars, replay, replayTime, replayTrailingTimes,
    computedIndicators, comparisonLines, comparisonWarning, overlayPoints,
    railEntries, chartEvidence, chartEventRows, openTab, plotMetric, indicatorActions,
    addIndicatorToLayout, addComparison,
  };
}
