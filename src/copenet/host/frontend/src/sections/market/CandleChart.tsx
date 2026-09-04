// TradingView Lightweight Charts (v5) candlestick + volume, themed to CopeNet's dark palette.
// Consumes the typed OHLCV series from the ticker payload. Pure presentation — no data fetching.
//
// SEC decorations are zoom-adaptive (operator-reviewed boxed-cluster design):
// event-days that crowd each other at the current zoom collapse into a cluster BOX spanning
// their time range and price range, tinted by net dollars, with a value-weighted average-price
// line and a minimal chip (▲9 ▼31 ●4 · net -$226M) that opens the range popup. Clusters are
// DERIVED from (events × visible range) on every pan/zoom — never stored — so new filings and
// zoom changes re-cluster for free. Days with room render as individual markers; markers only
// get text labels when nothing else is within LABEL_ROOM_PX. Zooming in dissolves boxes back
// into labeled markers because the same days stop overlapping.

import { useEffect, useRef, useState } from 'react';
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  LineSeries,
  LineType,
  PriceScaleMode,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { ChartEvent, EvidenceItem, Ohlcv } from './types';
import type { PriceAlert } from './types';
import { useChartWorkspace } from './drawings/useChartWorkspace';
import type { ChartWorkspaceBridge } from './drawings/types';
import { useChartPriceAlertLines } from './chartPriceAlerts';
import type { FinancialOverlayPoint } from './financialOverlay';
import type { ChartComparisonLine } from './chartComparison';
import type { InsiderDisplayMode } from './chartRanges';
import type { ComputedIndicator } from './indicators/compute';
import type { IndicatorRowActions } from './indicators/IndicatorRows';
import { IndicatorPaneControls } from './indicators/IndicatorPaneControls';
import { useChartIndicators } from './indicators/useChartIndicators';
import { replaceComparisonSeries } from './chartComparisonSeries';
import {
  hasRenderableFinancialOverlay,
  overlayAxisFormatter,
  splitFinancialOverlaySegments,
} from './financialOverlay';
import { MM, evidenceDate, evidenceTypeBg, evidenceTypeColor, mono, toneColor } from './marketUi';

import { BOX_BG, BOX_BORDER, LABEL_ROOM_PX, PRICE_PROBE_PX, barSpacingPx, bucketMarkers, buildBuckets, clusterBuckets, eventsAsEvidence, evidenceForDay, formatMoney, futureDecorations, individualMarkers, leftAxisWidth, normalize, pricePaneHeight, type DayPopupState, type RenderedBox } from './chartDecorations';

export function CandleChart({
  bars,
  events = [],
  evidence = [],
  height = 380,
  financialOverlay,
  financialOverlayKind,
  financialOverlayUnit,
  financialOverlayValuation = false,
  financialOverlayInverted = false,
  priceAlerts = [],
  draftAlertPrice,
  alertPlacementActive = false,
  onAlertPriceSelected,
  comparisonMode = false,
  comparisonLines = [],
  insiderDisplayMode = 'individual',
  logScale = false,
  showVolume = true,
  indicators = [],
  indicatorActions,
  indicatorPriceStretch,
  onIndicatorPaneStretch,
  onHoverBar,
  chartWorkspace,
}: {
  chartWorkspace?: ChartWorkspaceBridge;
  bars: Ohlcv[];
  events?: ChartEvent[];
  /** Full evidence rows backing the markers — clicking a marker day pops their details. */
  evidence?: EvidenceItem[];
  height?: number;
  /** Filing-date-aligned financial observations on their own left-side scale. */
  financialOverlay?: FinancialOverlayPoint[];
  /** Metric id — any entry from market.financial.metrics.list. */
  financialOverlayKind?: string;
  /** Unit the overlay observations carry (USD, ratio, USD/shares, shares). */
  financialOverlayUnit?: string;
  /** Valuation series step per price bar; financial series step per filing. */
  financialOverlayValuation?: boolean;
  /** Inverted valuations (yields) format as percentages instead of multiples. */
  financialOverlayInverted?: boolean;
  priceAlerts?: PriceAlert[];
  draftAlertPrice?: number | null;
  alertPlacementActive?: boolean;
  onAlertPriceSelected?: (price: number) => void;
  /** Volume is an ordinary plot the operator can remove, not a permanent fixture. */
  showVolume?: boolean;
  /** Technical indicators, already computed. Price overlays share the candle pane; the rest
   *  each get their own pane below it. The chart hands these straight to the indicator layer
   *  and never inspects them. */
  indicators?: ComputedIndicator[];
  /** Supplied when the operator may act on an indicator from the chart itself. Omitted, the
   *  pane heads still show their legend but carry no controls. */
  indicatorActions?: IndicatorRowActions;
  /** How much of the chart the price pane holds against each indicator pane. */
  indicatorPriceStretch: number;
  /** Fires when a pane separator has been dragged, so the division can be persisted. */
  onIndicatorPaneStretch?: (next: { priceStretch: number; byInstance: Record<string, number> }) => void;
  /** Crosshair bar under the pointer, or null when the pointer leaves the chart. Lets the
   *  legend live ON the chart instead of in a metadata strip wrapped around it. */
  onHoverBar?: (bar: Ohlcv | null) => void;
  comparisonMode?: boolean;
  comparisonLines?: ChartComparisonLine[];
  insiderDisplayMode?: InsiderDisplayMode;
  logScale?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const financialRef = useRef<ISeriesApi<'Line'> | null>(null);
  const financialSegmentRefs = useRef<ISeriesApi<'Line'>[]>([]);
  const comparisonRefs = useRef<ISeriesApi<'Line'>[]>([]);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const [dayPopup, setDayPopup] = useState<DayPopupState | null>(null);
  const [clusterBoxes, setClusterBoxes] = useState<RenderedBox[]>([]);
  const [chartGeneration, setChartGeneration] = useState(0);
  // Refs so the (once-subscribed) chart handlers always see current data.
  const evidenceRef = useRef<EvidenceItem[]>(evidence);
  const eventsRef = useRef<ChartEvent[]>(events);
  const barsRef = useRef<Ohlcv[]>(bars);
  const futureMarkersRef = useRef<SeriesMarker<Time>[]>([]);
  const alertPlacementRef = useRef(alertPlacementActive);
  const onAlertPriceSelectedRef = useRef(onAlertPriceSelected);
  const onHoverBarRef = useRef(onHoverBar);
  const workspaceRef = useRef(chartWorkspace);
  workspaceRef.current = chartWorkspace;
  const insiderDisplayModeRef = useRef(insiderDisplayMode);
  const rafRef = useRef<number | null>(null);
  evidenceRef.current = evidence;
  eventsRef.current = events;
  barsRef.current = bars;
  alertPlacementRef.current = alertPlacementActive;
  onAlertPriceSelectedRef.current = onAlertPriceSelected;
  onHoverBarRef.current = onHoverBar;
  insiderDisplayModeRef.current = insiderDisplayMode;
  useChartWorkspace(chartRef, candleRef, containerRef, chartGeneration, chartWorkspace, comparisonMode);
  useChartPriceAlertLines(candleRef, priceAlerts, chartGeneration, draftAlertPrice);
  const indicatorPaneRects = useChartIndicators(
    chartRef,
    chartGeneration,
    indicators,
    containerRef,
    indicatorPriceStretch,
    onIndicatorPaneStretch,
  );

  /** Recompute markers + cluster boxes for the current data and zoom. Derived, never stored:
   *  runs on data change and (rAF-throttled) on every visible-range change. */
  const recomputeDecorations = () => {
    const chart = chartRef.current;
    const candle = candleRef.current;
    const markersApi = markersRef.current;
    if (!chart || !candle || !markersApi) return;
    const rows = normalize(barsRef.current);
    if (!rows.length) {
      markersApi.setMarkers([]);
      setClusterBoxes([]);
      return;
    }
    const timeScale = chart.timeScale();
    const paneWidth = timeScale.width();
    if (paneWidth <= 0) return;
    // `timeToCoordinate` is PANE-relative, and the pane starts after the left price axis.
    // Cluster boxes are absolutely positioned against the wrapper, which starts at the
    // chart's left edge — so every pane x needs the axis width added back. This is zero
    // until a financial overlay makes the left scale visible, at which point every box
    // silently rendered one axis-width too far left.
    const leftAxisPx = leftAxisWidth(chart);

    const sourceEvidence = evidenceRef.current.length ? evidenceRef.current : eventsAsEvidence(eventsRef.current);
    const buckets = buildBuckets(sourceEvidence, rows);
    const xByTime = new Map<number, number>();
    for (const bucket of buckets) {
      const coordinate = timeScale.timeToCoordinate(bucket.time as UTCTimestamp);
      if (coordinate != null) xByTime.set(bucket.time, coordinate);
    }
    const individual = insiderDisplayModeRef.current === 'individual';
    const { clusters, loose } = individual ? { clusters: [], loose: buckets } : clusterBuckets(buckets, rows, xByTime);

    // Loose-day markers: text only when no other decorated day is nearby at this zoom.
    const allXs = [...xByTime.values()];
    const markers: SeriesMarker<Time>[] = [];
    for (const bucket of loose) {
      const x = xByTime.get(bucket.time);
      if (x == null) continue;
      let room = Number.POSITIVE_INFINITY;
      for (const other of allXs) {
        const d = Math.abs(other - x);
        if (d > 0.5 && d < room) room = d;
      }
      markers.push(...(individual ? individualMarkers(bucket) : bucketMarkers(bucket, room >= LABEL_ROOM_PX)));
    }
    markersApi.setMarkers([...markers, ...futureMarkersRef.current].sort((a, z) => (a.time as number) - (z.time as number)));

    const boxes: RenderedBox[] = [];
    clusters.forEach((cluster, ci) => {
      const first = cluster.buckets[0];
      const last = cluster.buckets[cluster.buckets.length - 1];
      const firstX = xByTime.get(first.time);
      const lastX = xByTime.get(last.time);
      if (firstX == null || lastX == null) return;
      const halfBar = Math.max(2, barSpacingPx(timeScale, rows) / 2);
      let left = firstX - halfBar - 2;
      let right = lastX + halfBar + 2;
      if (right < 0 || left > paneWidth) return; // fully off-screen
      left = Math.max(0, left);
      right = Math.min(paneWidth, right);
      const hi = Math.max(...cluster.buckets.map((b) => rows[b.barIndex].h));
      const lo = Math.min(...cluster.buckets.map((b) => rows[b.barIndex].l));
      const topCoord = candle.priceToCoordinate(hi);
      const botCoord = candle.priceToCoordinate(lo);
      if (topCoord == null || botCoord == null) return;
      const top = Math.max(0, Math.min(topCoord, botCoord) - 10);
      const bottom = Math.min(pricePaneHeight(chart, height - 24), Math.max(topCoord, botCoord) + 10);
      if (bottom - top < 8) return;
      const avgCoord = cluster.avgPrice != null ? candle.priceToCoordinate(cluster.avgPrice) : null;
      const tone: RenderedBox['tone'] = cluster.net > 0 ? 'up' : cluster.net < 0 ? 'down' : 'flat';
      const parts: string[] = [];
      if (cluster.buys) parts.push(`▲${cluster.buys}`);
      if (cluster.sells) parts.push(`▼${cluster.sells}`);
      if (cluster.neutral) parts.push(`●${cluster.neutral}`);
      const chip = `${parts.join(' ')}${cluster.net ? ` · net ${formatMoney(cluster.net)}` : ''}`;
      boxes.push({
        key: `${first.time}-${last.time}-${ci}`,
        // Clipping above is done in pane coordinates; only the rendered position needs
        // shifting into wrapper space.
        left: left + leftAxisPx,
        top,
        width: right - left,
        height: bottom - top,
        avgY: avgCoord != null && avgCoord > top + 4 && avgCoord < bottom - 4 ? avgCoord : null,
        avgPrice: cluster.avgPrice,
        avgSide: cluster.avgSide,
        chip,
        tone,
        items: [...cluster.items].sort((a, z) => (z.t ?? 0) - (a.t ?? 0)),
        firstTime: first.time,
        rangeLabel: `${evidenceDate(first.time)} – ${evidenceDate(last.time)}`,
      });
    });
    setClusterBoxes(boxes);
  };
  const recomputeRef = useRef(recomputeDecorations);
  recomputeRef.current = recomputeDecorations;

  /** Recompute only if either axis transform actually moved.
   *
   *  Lightweight Charts publishes a visible-time-range event but nothing at all for the
   *  price scale, so a vertical change — price-axis drag, vertical pan, autoscale shift —
   *  has no event to hang off. Comparing the two mappings catches every case uniformly.
   *  Two price probes rather than one, because a rescale pivoting exactly on a single
   *  probe would leave its coordinate unchanged. */
  const transformKeyRef = useRef('');
  const syncDecorations = () => {
    const chart = chartRef.current;
    const candle = candleRef.current;
    if (!chart || !candle) return;
    const range = chart.timeScale().getVisibleLogicalRange();
    const key = [
      range?.from ?? '',
      range?.to ?? '',
      candle.coordinateToPrice(0) ?? '',
      candle.coordinateToPrice(PRICE_PROBE_PX) ?? '',
      // Showing or hiding the left financial axis moves the pane sideways without
      // touching either range, so it has to be part of the transform identity.
      leftAxisWidth(chart),
      // Adding or removing an indicator pane resizes the price pane vertically. The price
      // probes above catch that in most cases, but not a rescale that happens to preserve
      // both sample coordinates, so measure the pane itself too.
      pricePaneHeight(chart, height),
    ].join('|');
    if (key === transformKeyRef.current) return;
    transformKeyRef.current = key;
    recomputeRef.current();
  };
  const syncRef = useRef(syncDecorations);
  syncRef.current = syncDecorations;

  // create once
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      width: el.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: MM.muted,
        fontFamily: "'IBM Plex Mono', monospace",
        fontSize: 10,
      },
      grid: { vertLines: { color: 'rgba(254,252,244,.04)' }, horzLines: { color: 'rgba(254,252,244,.04)' } },
      leftPriceScale: {
        visible: false,
        borderColor: 'rgba(254,252,244,.08)',
        textColor: MM.muted,
      },
      rightPriceScale: { borderColor: 'rgba(254,252,244,.08)' },
      timeScale: { borderColor: 'rgba(254,252,244,.08)', rightOffset: 4 },
      crosshair: { mode: 0 },
    });
    const candle = chart.addSeries(CandlestickSeries, {
      upColor: MM.up,
      downColor: MM.down,
      borderVisible: false,
      wickUpColor: MM.up,
      wickDownColor: MM.down,
    });
    const volume = chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol' });
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.84, bottom: 0 } });
    // Periodic financial observations step from the SEC filing date, never the
    // period end. The separate scale prevents fundamentals from distorting price.
    const financialSeries = chart.addSeries(LineSeries, {
      priceScaleId: 'left',
      color: '#8fb8e8',
      lineWidth: 2,
      lineType: LineType.WithSteps,
      pointMarkersVisible: true,
      lastValueVisible: true,
      priceLineVisible: false,
      crosshairMarkerVisible: true,
    });
    chart.priceScale('left').applyOptions({ scaleMargins: { top: 0.45, bottom: 0.2 }, visible: false });
    const markers = createSeriesMarkers(candle, []);

    // Feed the on-chart legend. Reading through refs keeps this subscription off the
    // chart-rebuild dependency list — the chart is torn down and recreated on height and
    // theme changes, and re-subscribing per render would leak handlers.
    chart.subscribeCrosshairMove((param) => {
      if (param.time == null) {
        onHoverBarRef.current?.(null);
        return;
      }
      const time = param.time as number;
      onHoverBarRef.current?.(barsRef.current.find((bar) => bar.t === time) ?? null);
    });

    // Click a marker day → popup with everything that hit that day (who, $, filing link).
    chart.subscribeClick((param) => {
      const workspace = workspaceRef.current;
      if (workspace?.enabled && (workspace.mode !== 'select' || workspace.objects.some((object) => object.id === param.hoveredObjectId))) {
        setDayPopup(null);
        return;
      }
      if (!param.point) {
        setDayPopup(null);
        return;
      }
      if (alertPlacementRef.current) {
        const price = candle.coordinateToPrice(param.point.y);
        if (price != null && Number.isFinite(price) && price > 0) onAlertPriceSelectedRef.current?.(price);
        setDayPopup(null);
        return;
      }
      if (param.time == null) {
        setDayPopup(null);
        return;
      }
      const time = param.time as number;
      const items = evidenceForDay(evidenceRef.current, normalize(barsRef.current), time);
      if (!items.length) {
        setDayPopup(null);
        return;
      }
      // Same pane-vs-wrapper offset as the cluster boxes: param.point.x is pane-relative.
      setDayPopup({ x: param.point.x + leftAxisWidth(chart), y: param.point.y, time, items });
    });

    // The day popup is anchored to a pixel position that stops meaning anything the moment
    // the chart moves underneath it.
    const onRangeChange = () => setDayPopup(null);
    chart.timeScale().subscribeVisibleLogicalRangeChange(onRangeChange);

    // Cluster boxes are absolutely-positioned HTML at pixel coordinates, so they have to
    // track BOTH axes, and a vertical change has no event to subscribe to.
    //
    // Pointer and wheel listeners cover the interactions that actually move the price
    // scale — dragging the axis, vertical pan, wheel zoom — and fire deterministically.
    // The rAF loop is the catch-all for everything else (autoscale settling, animated
    // range changes). It deliberately carries no load-bearing case of its own: rAF does
    // not run at all while the document is hidden, so anything relying on it exclusively
    // would silently stop working in a backgrounded tab.
    const onPointerSync = () => syncRef.current();
    for (const type of ['pointerdown', 'pointermove', 'pointerup', 'wheel'] as const) {
      el.addEventListener(type, onPointerSync, { passive: true });
    }
    const sampleTransform = () => {
      rafRef.current = requestAnimationFrame(sampleTransform);
      syncRef.current();
    };
    rafRef.current = requestAnimationFrame(sampleTransform);

    chartRef.current = chart;
    candleRef.current = candle;
    volumeRef.current = volume;
    financialRef.current = financialSeries;
    markersRef.current = markers;
    setChartGeneration((generation) => generation + 1);

    const ro = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
        recomputeRef.current();
      }
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      for (const type of ['pointerdown', 'pointermove', 'pointerup', 'wheel'] as const) {
        el.removeEventListener(type, onPointerSync);
      }
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(onRangeChange);
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      financialRef.current = null;
      financialSegmentRefs.current = [];
      comparisonRefs.current = [];
      markersRef.current = null;
    };
    // Deliberately empty: the chart is created once and mutated thereafter. Rebuilding it on
    // every height change threw away zoom and pan each time the research drawer resized.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Height is an option, not a reason to rebuild. The SEC cluster boxes are absolutely
  // positioned at priceToCoordinate pixels, so they have to be recomputed against the new
  // pane geometry — and only after the chart has actually repainted at the new size.
  useEffect(() => {
    const chart = chartRef.current;
    const container = containerRef.current;
    if (!chart || !container) return;
    // resize() rather than applyOptions({ height }) — the options path does not actually
    // re-lay-out the panes, so the chart kept its construction height while its region
    // shrank underneath it.
    chart.resize(container.clientWidth, height);
    transformKeyRef.current = '';
    const frame = requestAnimationFrame(() => syncRef.current());
    return () => cancelAnimationFrame(frame);
  }, [height]);

  // price-scale mode (runs after creation; also re-applies when the chart is rebuilt on height change)
  useEffect(() => {
    chartRef.current?.priceScale('right').applyOptions({ mode: logScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal });
    // Switching log/linear rewrites every price coordinate, so the boxes have to move with
    // it. Recomputing synchronously here does NOT work: applyOptions only invalidates the
    // scale, and priceToCoordinate keeps returning the old mapping until the chart
    // repaints. So invalidate the cached transform instead and let the next frame do the
    // work against a settled mapping.
    transformKeyRef.current = '';
    requestAnimationFrame(() => syncRef.current());
    try {
      localStorage.setItem('mm-log-scale', logScale ? '1' : '0');
    } catch {
      /* private mode — preference just doesn't persist */
    }
  }, [logScale, chartGeneration]);

  // update data
  useEffect(() => {
    const candle = candleRef.current;
    const volume = volumeRef.current;
    const chart = chartRef.current;
    if (!candle || !volume || !chart) return;
    const rows = normalize(bars);
    const sourceEvidence = evidence.length ? evidence : eventsAsEvidence(events);
    const future = futureDecorations(sourceEvidence, rows);
    futureMarkersRef.current = future.markers;
    // Whitespace points extend the time scale past the last candle so future-dated
    // planned-sale markers have a coordinate to land on.
    candle.setData([
      ...rows.map((b) => ({ time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c })),
      ...future.times.map((t) => ({ time: t as UTCTimestamp })),
    ]);
    volume.setData(
      rows.map((b) => ({ time: b.t as UTCTimestamp, value: b.v, color: b.c >= b.o ? 'rgba(105,197,137,.3)' : 'rgba(217,109,95,.3)' })),
    );
    chart.timeScale().fitContent();
    recomputeRef.current();
    // chartGeneration: a height change tears the chart down and builds a new one, so the
    // data has to be written again. Without this the chart comes back blank — latent while
    // height was effectively constant, immediate once the layout can resize it.
  }, [bars, events, evidence, chartGeneration]);

  useEffect(() => {
    const chart = chartRef.current;
    const candle = candleRef.current;
    const volume = volumeRef.current;
    if (!chart || !candle || !volume) return;
    const latestPrice = barsRef.current[barsRef.current.length - 1]?.c ?? 1;
    const pricePrecision = latestPrice < 1 ? 4 : 2;
    const comparisonValueMode = comparisonLines[0]?.valueMode ?? 'percent';
    candle.applyOptions({
      visible: !comparisonMode,
      lastValueVisible: !comparisonMode,
      priceFormat: comparisonMode && comparisonValueMode === 'percent'
        ? { type: 'custom', minMove: 0.01, formatter: (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(1)}%` }
        : { type: 'price', precision: pricePrecision, minMove: 10 ** -pricePrecision },
    });
    volume.applyOptions({ visible: !comparisonMode && showVolume });
    comparisonRefs.current = replaceComparisonSeries(
      chart,
      comparisonRefs.current,
      comparisonMode ? comparisonLines : [],
    );
    chart.timeScale().fitContent();
  }, [comparisonMode, comparisonLines, showVolume, chartGeneration]);

  // Overlay changes must not reset the operator's zoom. Underlying observations
  // stay periodic; the step is explicitly an availability-date visualization.
  useEffect(() => {
    const chart = chartRef.current;
    const primary = financialRef.current;
    if (!chart || !primary) return;
    for (const series of financialSegmentRefs.current) {
      chart.removeSeries(series);
    }
    financialSegmentRefs.current = [];
    // Lightweight Charts intentionally connects a line through whitespace data.
    // Separate series are therefore required for honest null/stale P/E gaps.
    const segments = splitFinancialOverlaySegments(financialOverlay ?? []);
    primary.setData(
      (segments[0] ?? []).map((point) => ({
        time: point.t as UTCTimestamp,
        value: point.value,
      })),
    );
    for (const segment of segments.slice(1)) {
      const series = chart.addSeries(LineSeries, {
        priceScaleId: 'left',
        color: '#d9ad67',
        lineWidth: 2,
        lineType: LineType.Simple,
        pointMarkersVisible: false,
        lastValueVisible: false,
        priceLineVisible: false,
        crosshairMarkerVisible: true,
      });
      series.setData(
        segment.map((point) => ({
          time: point.t as UTCTimestamp,
          value: point.value,
        })),
      );
      financialSegmentRefs.current.push(series);
    }
    recomputeRef.current();
  }, [financialOverlay, financialOverlayKind, chartGeneration]);

  useEffect(() => {
    const hasValues = !comparisonMode && financialOverlayKind != null
      && hasRenderableFinancialOverlay(financialOverlay);
    chartRef.current?.priceScale('left').applyOptions({
      visible: hasValues,
    });
    const series = [
      ...(financialRef.current ? [financialRef.current] : []),
      ...financialSegmentRefs.current,
    ];
    if (!hasValues) {
      // Lightweight Charts invokes custom price formatters with a null internal
      // value when an otherwise-visible scale has no renderable points. Keep the
      // empty overlay selected in the UI, but do not configure or expose its axis.
      series.forEach((item) => item.applyOptions({ lastValueVisible: false }));
      transformKeyRef.current = '';
      requestAnimationFrame(() => syncRef.current());
      return;
    }
    const formatter = overlayAxisFormatter(
      financialOverlayUnit,
      financialOverlayValuation,
      financialOverlayInverted,
    );
    const minMove = financialOverlayValuation || financialOverlayUnit === 'ratio' || financialOverlayUnit === 'USD/shares'
      ? 0.001
      : 1;
    series.forEach((item, index) => {
      item.applyOptions({
        color: financialOverlayValuation ? '#d9ad67' : '#8fb8e8',
        lineType: financialOverlayValuation ? LineType.Simple : LineType.WithSteps,
        pointMarkersVisible: !financialOverlayValuation,
        lastValueVisible: index === series.length - 1,
        priceFormat: { type: 'custom', minMove, formatter },
      });
    });
    // Toggling the overlay shows/hides the left axis, which slides the pane sideways.
    // Same repaint caveat as the log toggle: the new axis width is not readable until the
    // chart redraws, so invalidate and let the next frame reposition against it.
    transformKeyRef.current = '';
    requestAnimationFrame(() => syncRef.current());
  }, [comparisonMode, financialOverlayKind, financialOverlay, financialOverlayUnit, financialOverlayValuation, financialOverlayInverted, chartGeneration]);

  const popupNet = dayPopup
    ? dayPopup.items.reduce(
        (acc, item) => {
          if (item.type === 'Insider' && item.tone !== 'flat' && item.value) {
            acc.net += item.tone === 'up' ? item.value : -item.value;
            acc[item.tone === 'up' ? 'buys' : 'sells'] += 1;
          }
          return acc;
        },
        { net: 0, buys: 0, sells: 0 },
      )
    : null;

  return (
    <div style={{ position: 'relative', cursor: alertPlacementActive ? 'crosshair' : undefined }}>
      <div ref={containerRef} style={{ width: '100%' }} />
      {!comparisonMode && clusterBoxes.map((box) => (
        <div
          key={box.key}
          style={{
            position: 'absolute',
            left: box.left,
            top: box.top,
            width: box.width,
            height: box.height,
            zIndex: 4,
            pointerEvents: 'none',
            border: `1px solid ${BOX_BORDER[box.tone]}`,
            background: BOX_BG[box.tone],
            borderRadius: 6,
          }}
        >
          {box.avgY != null && (
            <>
              <div style={{ position: 'absolute', left: 0, right: 0, top: box.avgY - box.top, borderTop: `1px dashed ${toneColor(box.tone)}`, opacity: 0.75 }} />
              {box.height > 34 && box.avgPrice != null && (
                <span style={{ position: 'absolute', right: 3, top: Math.max(1, box.avgY - box.top - 12), fontFamily: mono, fontSize: 8.5, color: toneColor(box.tone), whiteSpace: 'nowrap' }}>
                  avg {box.avgSide} ${box.avgPrice.toFixed(2)}
                </span>
              )}
            </>
          )}
        </div>
      ))}
      {!comparisonMode && clusterBoxes.map((box) => (
        <button
          key={`chip-${box.key}`}
          onClick={() =>
            setDayPopup({
              x: box.left + box.width / 2,
              y: box.top + 10,
              time: box.firstTime,
              items: box.items,
              rangeLabel: box.rangeLabel,
            })
          }
          style={{
            position: 'absolute',
            left: box.left + box.width / 2,
            top: Math.max(2, box.top - 21),
            transform: 'translateX(-50%)',
            zIndex: 6,
            cursor: 'pointer',
            border: `1px solid ${BOX_BORDER[box.tone]}`,
            background: '#0b0b0d',
            color: box.tone === 'flat' ? MM.muted : toneColor(box.tone),
            borderRadius: 7,
            padding: '2px 7px',
            fontFamily: mono,
            fontSize: 9.5,
            whiteSpace: 'nowrap',
            lineHeight: 1.5,
          }}
        >
          {box.chip}
        </button>
      ))}
      {!comparisonMode && dayPopup && (
        <div
          style={{
            position: 'absolute',
            left: Math.min(dayPopup.x + 12, Math.max((containerRef.current?.clientWidth ?? 600) - 372, 8)),
            top: Math.max(Math.min(dayPopup.y, height - 240), 8),
            zIndex: 10,
            width: 360,
            maxHeight: 260,
            overflowY: 'auto',
            background: '#0b0b0d',
            border: `1px solid ${MM.borderHi}`,
            borderRadius: 12,
            padding: 12,
            boxShadow: '0 16px 32px rgba(0,0,0,.55)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 8 }}>
            <span style={{ font: '600 9px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.accent }}>
              SEC activity · {dayPopup.rangeLabel ?? evidenceDate(dayPopup.time)}
            </span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              {popupNet && (popupNet.buys || popupNet.sells) ? (
                <span style={{ fontFamily: mono, fontSize: 10, color: popupNet.net > 0 ? MM.up : popupNet.net < 0 ? MM.down : MM.muted }}>
                  net {formatMoney(popupNet.net)} · {popupNet.buys}B/{popupNet.sells}S
                </span>
              ) : null}
              <button onClick={() => setDayPopup(null)} style={{ cursor: 'pointer', border: 'none', background: 'transparent', color: MM.dim, fontSize: 13, lineHeight: 1, padding: 0 }}>×</button>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {dayPopup.items.map((item, i) => (
              <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 8, padding: '7px 0', borderTop: i ? `1px solid rgba(254,252,244,.05)` : 'none' }}>
                <span style={{ flex: '0 0 auto', borderRadius: 5, padding: '2px 6px', font: '600 8px var(--mkt-sans)', letterSpacing: '.06em', textTransform: 'uppercase', background: evidenceTypeBg(item.type), color: evidenceTypeColor(item.type) }}>{item.type}</span>
                <span style={{ flex: 1, minWidth: 0, fontSize: 11, color: MM.textSoft, lineHeight: 1.45 }}>
                  {item.tone !== 'flat' && <span style={{ fontFamily: mono, fontSize: 10, color: toneColor(item.tone), marginRight: 5 }}>{item.tone === 'up' ? '▲' : '▼'}</span>}
                  {item.headline}
                  {item.value != null && item.value !== 0 && <span style={{ fontFamily: mono, fontSize: 10.5, color: toneColor(item.tone), marginLeft: 6 }}>{formatMoney(item.value)}</span>}
                  {item.value === 0 && <span style={{ fontFamily: mono, fontSize: 10, color: MM.dim, marginLeft: 6 }}>no cash moved</span>}
                  {dayPopup.rangeLabel && evidenceDate(item.t) && (
                    <span style={{ fontFamily: mono, fontSize: 9.5, color: MM.dimmer, marginLeft: 6 }}>{evidenceDate(item.t)}</span>
                  )}
                </span>
                {item.url && (
                  <a href={item.url} target="_blank" rel="noreferrer" title="Open the SEC filing" style={{ flex: '0 0 auto', fontSize: 10, color: '#8fb8e8', textDecoration: 'none', whiteSpace: 'nowrap' }}>
                    filing ↗
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
      <IndicatorPaneControls
        rects={indicatorPaneRects}
        indicators={indicators}
        actions={indicatorActions}
      />
      {alertPlacementActive && (
        <span style={{ position: 'absolute', top: 8, left: '50%', zIndex: 12, transform: 'translateX(-50%)', border: `1px solid rgba(251,148,35,.35)`, borderRadius: 7, background: '#0b0b0d', color: MM.accent, padding: '5px 9px', font: '700 9px var(--mkt-sans)', letterSpacing: '.04em', pointerEvents: 'none' }}>
          Click the chart to place a daily-close alert
        </span>
      )}
      {bars.length === 0 && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: MM.dim, fontSize: 12, fontStyle: 'italic', pointerEvents: 'none' }}>
          Loading candles…
        </div>
      )}
    </div>
  );
}
