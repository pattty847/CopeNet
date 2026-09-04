// SEC marker clustering and candle coordinate helpers.
import type { IChartApi, SeriesMarker, Time, UTCTimestamp } from 'lightweight-charts';
import type { ChartEvent, EvidenceItem, Ohlcv } from './types';
import { MM } from './marketUi';

// ---- clustering thresholds ----
// Distances are in PIXELS, which is the zoom-aware version of "n candles apart":
// px = candles × current bar spacing, so the same two days cluster on a phone and
// stand alone on a wide desktop view.
export const CLUSTER_GAP_PX = 28; // event-days closer than this chain into one time-cluster
export const LABEL_ROOM_PX = 56; // a lone marker gets text only with this much space around it
export const MIN_CLUSTER_EVENTS = 3; // smaller groups stay as plain markers
export const MIN_CLUSTER_DAYS = 2; // single busy days are served by the day popup, not a box
export const PRICE_SPLIT_FRACTION = 0.06; // split a time-cluster where price shelves gap >6%
export const PRICE_PROBE_PX = 100; // second sample point for detecting vertical rescales

/** Lightweight Charts briefly detaches a newly shown price scale while recalculating its
 *  pane. Calling width() in that frame throws even though the chart and scale API are both
 *  live; zero is the correct pre-layout offset and the next transform sample settles it. */
export function leftAxisWidth(chart: IChartApi): number {
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
export function pricePaneHeight(chart: IChartApi, fallback: number): number {
  try {
    const size = chart.paneSize(0);
    return size.height > 0 ? size.height : fallback;
  } catch {
    return fallback;
  }
}

export function formatMoney(value: number): string {
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
export function barSpacingPx(
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
export function snapToBar(t: number, times: number[]): number {
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

export interface DayPopupState {
  x: number;
  y: number;
  time: number;
  items: EvidenceItem[];
  /** Set when the popup covers a cluster's date range instead of a single day. */
  rangeLabel?: string;
}

/** All evidence snapped to a given bar time — what actually "hit" that day. */
export function evidenceForDay(evidence: EvidenceItem[], bars: Ohlcv[], time: number): EvidenceItem[] {
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
export function normalize(bars: Ohlcv[]): Ohlcv[] {
  const byTime = new Map<number, Ohlcv>();
  for (const b of bars) {
    if (b && Number.isFinite(b.t)) byTime.set(b.t, b);
  }
  return [...byTime.entries()].sort((a, z) => a[0] - z[0]).map(([, b]) => b);
}

export type Glyph = '▲' | '▼' | '●' | '▽' | '8-K';

/** Same glyph semantics as the backend's chart_events_from_evidence. */
export function glyphFor(item: EvidenceItem): Glyph {
  if (item.type === 'Insider') return item.tone === 'up' ? '▲' : item.tone === 'down' ? '▼' : '●';
  if (item.type === 'Form 144') return '▽';
  return '8-K';
}

/** Fallback when a caller supplies thin ChartEvents without full evidence rows. */
export function eventsAsEvidence(events: ChartEvent[]): EvidenceItem[] {
  return events.map((e) => ({
    type: e.kind === 'insider' ? 'Insider' : e.kind === 'planned-sale' ? 'Form 144' : '8-K',
    symbol: '',
    headline: '',
    source: '',
    tone: e.glyph === '▲' ? 'up' : e.glyph === '▼' || e.glyph === '▽' ? 'down' : 'flat',
    t: e.t,
  }));
}

export interface DayBucket {
  time: number;
  barIndex: number;
  items: EvidenceItem[];
}

export function buildBuckets(evidence: EvidenceItem[], rows: Ohlcv[]): DayBucket[] {
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
export function anchorPrice(bucket: DayBucket, rows: Ohlcv[]): number {
  const priced = bucket.items
    .map((i) => i.price)
    .filter((p): p is number => typeof p === 'number' && Number.isFinite(p) && p > 0);
  if (priced.length) return priced.reduce((a, b) => a + b, 0) / priced.length;
  return rows[bucket.barIndex]?.c ?? 0;
}

export interface ClusterSummary {
  buckets: DayBucket[]; // sorted by barIndex
  items: EvidenceItem[];
  buys: number;
  sells: number;
  neutral: number;
  net: number; // tone-signed insider dollars (executed Form 4s only)
  avgPrice: number | null; // value-weighted avg price of the dominant direction
  avgSide: 'buy' | 'sell';
}

export function summarizeCluster(buckets: DayBucket[]): ClusterSummary {
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
export function clusterBuckets(
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
export function bucketMarkers(bucket: DayBucket, withText: boolean): SeriesMarker<UTCTimestamp>[] {
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

export function individualMarkers(bucket: DayBucket): SeriesMarker<UTCTimestamp>[] {
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
export function futureDecorations(evidence: EvidenceItem[], rows: Ohlcv[]): { markers: SeriesMarker<Time>[]; times: number[] } {
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

export interface RenderedBox {
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

export const BOX_BORDER: Record<RenderedBox['tone'], string> = {
  up: 'rgba(105,197,137,.35)',
  down: 'rgba(217,109,95,.35)',
  flat: 'rgba(254,252,244,.18)',
};
export const BOX_BG: Record<RenderedBox['tone'], string> = {
  up: 'rgba(105,197,137,.06)',
  down: 'rgba(217,109,95,.06)',
  flat: 'rgba(254,252,244,.03)',
};
