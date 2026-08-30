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
import { useChartPriceAlertLines } from './chartPriceAlerts';
import type { FinancialOverlayPoint } from './financialOverlay';
import type { ChartComparisonLine } from './chartComparison';
import type { InsiderDisplayMode } from './chartRanges';
import type { ComputedIndicator } from './indicators/compute';
import { useChartIndicators } from './indicators/useChartIndicators';
import { replaceComparisonSeries } from './chartComparisonSeries';
import {
  hasRenderableFinancialOverlay,
  overlayAxisFormatter,
  splitFinancialOverlaySegments,
} from './financialOverlay';
import { MM, evidenceDate, evidenceTypeBg, evidenceTypeColor, mono, toneColor } from './marketUi';

// ---- clustering thresholds ----
// Distances are in PIXELS, which is the zoom-aware version of "n candles apart":
// px = candles × current bar spacing, so the same two days cluster on a phone and
// stand alone on a wide desktop view.
const CLUSTER_GAP_PX = 28; // event-days closer than this chain into one time-cluster
const LABEL_ROOM_PX = 56; // a lone marker gets text only with this much space around it
const MIN_CLUSTER_EVENTS = 3; // smaller groups stay as plain markers
const MIN_CLUSTER_DAYS = 2; // single busy days are served by the day popup, not a box
const PRICE_SPLIT_FRACTION = 0.06; // split a time-cluster where price shelves gap >6%
const PRICE_PROBE_PX = 100; // second sample point for detecting vertical rescales

/** Lightweight Charts briefly detaches a newly shown price scale while recalculating its
 *  pane. Calling width() in that frame throws even though the chart and scale API are both
 *  live; zero is the correct pre-layout offset and the next transform sample settles it. */
function leftAxisWidth(chart: IChartApi): number {
  try {
    return chart.priceScale('left').width();
  } catch {
    return 0;
  }
}

/** Usable height of the PRICE pane.
 *
 *  Cluster boxes are absolutely-positioned HTML clamped to this. It used to be the chart's
 *  own height less a guess at the time axis, which was close enough while the price pane was
 *  the only pane. Indicator panes stack below it, so that clamp would now let a box overhang
 *  into an RSI pane. Pane 0 is always the price pane and always starts at y=0, so its
 *  measured height is both the correct clamp and the reason the rest of this positioning
 *  code needs no pane awareness at all. */
function pricePaneHeight(chart: IChartApi, fallback: number): number {
  try {
    const size = chart.paneSize(0);
    return size.height > 0 ? size.height : fallback;
  } catch {
    return fallback;
  }
}

function formatMoney(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${Math.round(abs).toLocaleString()}`;
}

/** On-screen width of one candle, measured rather than read from chart options.
 *
 *  `timeScale().options().barSpacing` is the *configured* value, which does not track live
 *  zoom, and it is expressed in slots — which stops meaning "one candle" the moment any
 *  other series contributes timestamps the candles do not have. Measuring two adjacent
 *  candle coordinates is immune to both. */
function barSpacingPx(
  timeScale: ReturnType<IChartApi['timeScale']>,
  rows: Ohlcv[],
): number {
  if (rows.length < 2) return 6;
  const mid = Math.floor(rows.length / 2);
  const left = timeScale.timeToCoordinate(rows[mid - 1].t as UTCTimestamp);
  const right = timeScale.timeToCoordinate(rows[mid].t as UTCTimestamp);
  if (left == null || right == null) return timeScale.options().barSpacing;
  return Math.abs(right - left);
}

/** Snap a unix-seconds timestamp to the nearest bar time (shared by markers and click lookups). */
function snapToBar(t: number, times: number[]): number {
  let nearest = times[0];
  let bestDiff = Math.abs(times[0] - t);
  for (const candidate of times) {
    const diff = Math.abs(candidate - t);
    if (diff < bestDiff) {
      nearest = candidate;
      bestDiff = diff;
    }
  }
  return nearest;
}

interface DayPopupState {
  x: number;
  y: number;
  time: number;
  items: EvidenceItem[];
  /** Set when the popup covers a cluster's date range instead of a single day. */
  rangeLabel?: string;
}

/** All evidence snapped to a given bar time — what actually "hit" that day. */
function evidenceForDay(evidence: EvidenceItem[], bars: Ohlcv[], time: number): EvidenceItem[] {
  if (!bars.length) return [];
  const times = bars.map((b) => b.t);
  const lastTime = times[times.length - 1];
  const barSpacing = times.length > 1 ? lastTime - times[times.length - 2] : 86400;
  return evidence.filter((item) => {
    if (!item.t || !Number.isFinite(item.t)) return false;
    if (item.t > lastTime + barSpacing) return item.t === time; // future whitespace: exact match
    return snapToBar(item.t, times) === time;
  });
}

/** Sort ascending + de-dupe by time (lightweight-charts requires strictly increasing unique times).
 *  The backend emits `t` as a UNIX timestamp in SECONDS — which is exactly what lightweight-charts'
 *  UTCTimestamp wants, so pass it through directly (no /1000). */
function normalize(bars: Ohlcv[]): Ohlcv[] {
  const byTime = new Map<number, Ohlcv>();
  for (const b of bars) {
    if (b && Number.isFinite(b.t)) byTime.set(b.t, b);
  }
  return [...byTime.entries()].sort((a, z) => a[0] - z[0]).map(([, b]) => b);
}

type Glyph = '▲' | '▼' | '●' | '▽' | '8-K';

/** Same glyph semantics as the backend's chart_events_from_evidence. */
function glyphFor(item: EvidenceItem): Glyph {
  if (item.type === 'Insider') return item.tone === 'up' ? '▲' : item.tone === 'down' ? '▼' : '●';
  if (item.type === 'Form 144') return '▽';
  return '8-K';
}

/** Fallback when a caller supplies thin ChartEvents without full evidence rows. */
function eventsAsEvidence(events: ChartEvent[]): EvidenceItem[] {
  return events.map((e) => ({
    type: e.kind === 'insider' ? 'Insider' : e.kind === 'planned-sale' ? 'Form 144' : '8-K',
    symbol: '',
    headline: '',
    source: '',
    tone: e.glyph === '▲' ? 'up' : e.glyph === '▼' || e.glyph === '▽' ? 'down' : 'flat',
    t: e.t,
  }));
}

interface DayBucket {
  time: number;
  barIndex: number;
  items: EvidenceItem[];
}

function buildBuckets(evidence: EvidenceItem[], rows: Ohlcv[]): DayBucket[] {
  if (!rows.length) return [];
  const times = rows.map((b) => b.t);
  const lastTime = times[times.length - 1];
  const barSpacing = times.length > 1 ? lastTime - times[times.length - 2] : 86400;
  const indexByTime = new Map(times.map((t, i) => [t, i] as const));
  const byTime = new Map<number, EvidenceItem[]>();
  for (const item of evidence) {
    if (!item.t || !Number.isFinite(item.t)) continue;
    if (item.t > lastTime + barSpacing) continue; // future-dated 144s handled separately
    // Bound the low end too. `snapToBar` finds the NEAREST bar, so an event older than the
    // chart would otherwise pile onto the first candle and read as activity that happened
    // on-screen. Snapping is presentation-only; it must never relocate an event's date.
    if (item.t < times[0] - barSpacing) continue;
    const snapped = snapToBar(item.t, times);
    byTime.set(snapped, [...(byTime.get(snapped) ?? []), item]);
  }
  return [...byTime.entries()]
    .map(([time, items]) => ({ time, barIndex: indexByTime.get(time) ?? 0, items }))
    .sort((a, z) => a.barIndex - z.barIndex);
}

/** A day's price anchor: mean of its real transaction prices, else the candle close. */
function anchorPrice(bucket: DayBucket, rows: Ohlcv[]): number {
  const priced = bucket.items
    .map((i) => i.price)
    .filter((p): p is number => typeof p === 'number' && Number.isFinite(p) && p > 0);
  if (priced.length) return priced.reduce((a, b) => a + b, 0) / priced.length;
  return rows[bucket.barIndex]?.c ?? 0;
}

interface ClusterSummary {
  buckets: DayBucket[]; // sorted by barIndex
  items: EvidenceItem[];
  buys: number;
  sells: number;
  neutral: number;
  net: number; // tone-signed insider dollars (executed Form 4s only)
  avgPrice: number | null; // value-weighted avg price of the dominant direction
  avgSide: 'buy' | 'sell';
}

function summarizeCluster(buckets: DayBucket[]): ClusterSummary {
  const items = buckets.flatMap((b) => b.items);
  let buys = 0;
  let sells = 0;
  let neutral = 0;
  let net = 0;
  for (const it of items) {
    const g = glyphFor(it);
    if (g === '▲') buys += 1;
    else if (g === '▼' || g === '▽') sells += 1;
    else neutral += 1;
    if (it.type === 'Insider' && it.tone !== 'flat' && it.value) net += it.tone === 'up' ? it.value : -it.value;
  }
  const avgSide: 'buy' | 'sell' = net > 0 ? 'buy' : 'sell';
  const sideTone = avgSide === 'buy' ? 'up' : 'down';
  let priceVolume = 0;
  let shareCount = 0;
  for (const it of items) {
    if (it.type !== 'Insider' || it.tone !== sideTone) continue;
    if (it.price && it.shares) {
      priceVolume += it.price * it.shares;
      shareCount += it.shares;
    }
  }
  return { buckets, items, buys, sells, neutral, net, avgPrice: shareCount > 0 ? priceVolume / shareCount : null, avgSide };
}

/** Chain day-buckets by pixel gap, then split each chain where its days sit on clearly
 *  different price shelves — two boxes, not one giant one. */
function clusterBuckets(
  buckets: DayBucket[],
  rows: Ohlcv[],
  xByTime: Map<number, number>,
): { clusters: ClusterSummary[]; loose: DayBucket[] } {
  const chains: DayBucket[][] = [];
  let chain: DayBucket[] = [];
  for (const bucket of buckets) {
    if (!chain.length) {
      chain = [bucket];
      continue;
    }
    const previousX = xByTime.get(chain[chain.length - 1].time);
    const currentX = xByTime.get(bucket.time);
    const gapPx = (
      previousX == null || currentX == null
        ? Number.POSITIVE_INFINITY
        : Math.abs(currentX - previousX)
    );
    if (gapPx <= CLUSTER_GAP_PX) chain.push(bucket);
    else {
      chains.push(chain);
      chain = [bucket];
    }
  }
  if (chain.length) chains.push(chain);

  const clusters: ClusterSummary[] = [];
  const loose: DayBucket[] = [];
  for (const c of chains) {
    const byPrice = [...c].sort((a, z) => anchorPrice(a, rows) - anchorPrice(z, rows));
    const groups: DayBucket[][] = [];
    let group: DayBucket[] = [];
    for (const bucket of byPrice) {
      if (!group.length) {
        group = [bucket];
        continue;
      }
      const prev = anchorPrice(group[group.length - 1], rows);
      const curr = anchorPrice(bucket, rows);
      if (prev > 0 && (curr - prev) / prev > PRICE_SPLIT_FRACTION) {
        groups.push(group);
        group = [bucket];
      } else {
        group.push(bucket);
      }
    }
    if (group.length) groups.push(group);
    for (const g of groups) {
      const ordered = [...g].sort((a, z) => a.barIndex - z.barIndex);
      const eventCount = ordered.reduce((n, b) => n + b.items.length, 0);
      if (ordered.length >= MIN_CLUSTER_DAYS && eventCount >= MIN_CLUSTER_EVENTS) clusters.push(summarizeCluster(ordered));
      else loose.push(...ordered);
    }
  }
  loose.sort((a, z) => a.barIndex - z.barIndex);
  return { clusters, loose };
}

/** Markers for one un-clustered day. Text only when the day has room at this zoom. */
function bucketMarkers(bucket: DayBucket, withText: boolean): SeriesMarker<UTCTimestamp>[] {
  const time = bucket.time as UTCTimestamp;
  let buys = 0;
  let sells = 0;
  let neutral = 0;
  let planned = 0;
  let filings = 0;
  for (const item of bucket.items) {
    const g = glyphFor(item);
    if (g === '▲') buys += 1;
    else if (g === '▼') sells += 1;
    else if (g === '●') neutral += 1;
    else if (g === '▽') planned += 1;
    else filings += 1;
  }
  const text = (label: string) => (withText ? label : undefined);
  const markers: SeriesMarker<UTCTimestamp>[] = [];
  if (buys) markers.push({ time, position: 'belowBar', shape: 'arrowUp', color: MM.up, size: 1, text: text(buys > 1 ? `${buys} insider buys` : 'insider buy') });
  if (sells) markers.push({ time, position: 'aboveBar', shape: 'arrowDown', color: MM.down, size: 1, text: text(sells > 1 ? `${sells} insider sells` : 'insider sell') });
  if (neutral) markers.push({ time, position: 'aboveBar', shape: 'circle', color: MM.dim, size: 0.6, text: text(neutral > 1 ? `${neutral} insider transfers` : 'insider transfer') });
  if (planned) markers.push({ time, position: 'aboveBar', shape: 'circle', color: MM.down, size: 0.7, text: text(planned > 1 ? `${planned} planned sales (144)` : 'planned sale (144)') });
  if (filings) markers.push({ time, position: 'aboveBar', shape: 'square', color: MM.muted, size: 0.6, text: text(filings > 1 ? `${filings} 8-Ks` : '8-K') });
  return markers;
}

function individualMarkers(bucket: DayBucket): SeriesMarker<UTCTimestamp>[] {
  return bucket.items.map((item) => {
    const glyph = glyphFor(item);
    const trade = item.type === 'Insider';
    const price = item.price && item.price > 0 ? ` @ $${item.price.toFixed(2)}` : '';
    const value = item.value ? ` ${formatMoney(item.value)}` : '';
    const text = trade ? `${glyph}${value}${price}` : item.type;
    return {
      time: bucket.time as UTCTimestamp,
      position: item.tone === 'up' ? 'belowBar' : 'aboveBar',
      shape: item.tone === 'up' ? 'arrowUp' : item.tone === 'down' ? 'arrowDown' : item.type === '8-K' ? 'square' : 'circle',
      color: item.tone === 'up' ? MM.up : item.tone === 'down' ? MM.down : MM.muted,
      size: trade ? 1 : 0.7,
      text,
    } satisfies SeriesMarker<UTCTimestamp>;
  });
}

/** Future-dated planned sales: whitespace times past the last candle + price-anchored markers. */
function futureDecorations(evidence: EvidenceItem[], rows: Ohlcv[]): { markers: SeriesMarker<Time>[]; times: number[] } {
  if (!evidence.length || !rows.length) return { markers: [], times: [] };
  const lastTime = rows[rows.length - 1].t;
  const lastClose = rows[rows.length - 1].c;
  const barSpacing = rows.length > 1 ? lastTime - rows[rows.length - 2].t : 86400;
  const markers: SeriesMarker<Time>[] = [];
  const times = new Set<number>();
  for (const item of evidence) {
    if (!item.t || item.t <= lastTime + barSpacing) continue;
    if (item.type !== 'Form 144') continue; // only planned sales are meaningfully future-dated
    times.add(item.t);
    markers.push({
      time: item.t as UTCTimestamp,
      position: 'atPriceMiddle',
      price: lastClose,
      shape: 'circle',
      color: MM.down,
      size: 1,
      text: 'planned sale (144)',
    });
  }
  return { markers, times: [...times].sort((a, z) => a - z) };
}

interface RenderedBox {
  key: string;
  left: number;
  top: number;
  width: number;
  height: number;
  avgY: number | null;
  avgPrice: number | null;
  avgSide: 'buy' | 'sell';
  chip: string;
  tone: 'up' | 'down' | 'flat';
  items: EvidenceItem[];
  firstTime: number;
  rangeLabel: string;
}

const BOX_BORDER: Record<RenderedBox['tone'], string> = {
  up: 'rgba(105,197,137,.35)',
  down: 'rgba(217,109,95,.35)',
  flat: 'rgba(254,252,244,.18)',
};
const BOX_BG: Record<RenderedBox['tone'], string> = {
  up: 'rgba(105,197,137,.06)',
  down: 'rgba(217,109,95,.06)',
  flat: 'rgba(254,252,244,.03)',
};

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
  onHoverBar,
}: {
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
  const insiderDisplayModeRef = useRef(insiderDisplayMode);
  const rafRef = useRef<number | null>(null);
  evidenceRef.current = evidence;
  eventsRef.current = events;
  barsRef.current = bars;
  alertPlacementRef.current = alertPlacementActive;
  onAlertPriceSelectedRef.current = onAlertPriceSelected;
  onHoverBarRef.current = onHoverBar;
  insiderDisplayModeRef.current = insiderDisplayMode;
  useChartPriceAlertLines(candleRef, priceAlerts, chartGeneration, draftAlertPrice);
  useChartIndicators(chartRef, chartGeneration, indicators);

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
        fontFamily: "'JetBrains Mono', monospace",
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
    candle.applyOptions({
      visible: !comparisonMode,
      lastValueVisible: !comparisonMode,
      priceFormat: comparisonMode
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
            <span style={{ font: '600 9px Inter', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.accent }}>
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
                <span style={{ flex: '0 0 auto', borderRadius: 5, padding: '2px 6px', font: '600 8px Inter', letterSpacing: '.06em', textTransform: 'uppercase', background: evidenceTypeBg(item.type), color: evidenceTypeColor(item.type) }}>{item.type}</span>
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
      {alertPlacementActive && (
        <span style={{ position: 'absolute', top: 8, left: '50%', zIndex: 12, transform: 'translateX(-50%)', border: `1px solid rgba(251,148,35,.35)`, borderRadius: 7, background: '#0b0b0d', color: MM.accent, padding: '5px 9px', font: '700 9px Inter', letterSpacing: '.04em', pointerEvents: 'none' }}>
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
