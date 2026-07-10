// TradingView Lightweight Charts (v5) candlestick + volume, themed to CopeNet's dark palette.
// Consumes the typed OHLCV series from the ticker payload. Pure presentation — no data fetching.

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
import { MM, evidenceDate, evidenceTypeBg, evidenceTypeColor, mono, toneColor } from './marketUi';

export interface RevenuePoint {
  t: number; // unix seconds (quarter end)
  value: number; // dollars
}

function formatRevenue(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (magnitude >= 1e6) return `$${(value / 1e6).toFixed(0)}M`;
  return `$${Math.round(value).toLocaleString()}`;
}

function formatMoney(value: number): string {
  const abs = Math.abs(value);
  const sign = value < 0 ? '-' : '';
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(0)}K`;
  return `${sign}$${Math.round(abs).toLocaleString()}`;
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

/** Insider/8-K event dates rarely land exactly on a candle's timestamp, but lightweight-charts
 *  markers only render on a time that matches an existing data point — so snap each event to its
 *  nearest bar. Future-dated planned sales (Form 144) get their own treatment: the time scale is
 *  extended with whitespace points past the last candle and the marker is anchored at the last
 *  close via a price-positioned marker, so upcoming sales are visible ON the chart, in the future. */
function decorationsFor(events: ChartEvent[], bars: Ohlcv[]): { markers: SeriesMarker<Time>[]; futureTimes: number[] } {
  if (!events.length || !bars.length) return { markers: [], futureTimes: [] };
  const times = bars.map((b) => b.t);
  const lastTime = times[times.length - 1];
  const lastClose = bars[bars.length - 1].c;
  const barSpacing = times.length > 1 ? lastTime - times[times.length - 2] : 86400;
  const futureMarkers: SeriesMarker<Time>[] = [];
  const futureTimes = new Set<number>();
  const grouped = new Map<number, ChartEvent[]>();
  for (const event of events) {
    if (!Number.isFinite(event.t)) continue;
    if (event.t > lastTime + barSpacing) {
      // Only planned sales are meaningfully future-dated; anchor at the last close.
      if (event.kind === 'planned-sale') {
        futureTimes.add(event.t);
        futureMarkers.push({
          time: event.t as UTCTimestamp,
          position: 'atPriceMiddle',
          price: lastClose,
          shape: 'circle',
          color: MM.down,
          size: 1,
          text: 'planned sale (144)',
        });
      }
      continue;
    }
    const nearest = snapToBar(event.t, times);
    const bucket = grouped.get(nearest) ?? [];
    bucket.push(event);
    grouped.set(nearest, bucket);
  }
  const markers: SeriesMarker<UTCTimestamp>[] = [];
  for (const [time, bucket] of grouped) {
    const insiderBuys = bucket.filter((e) => e.kind === 'insider' && e.glyph === '▲').length;
    const insiderSells = bucket.filter((e) => e.kind === 'insider' && e.glyph === '▼').length;
    const filings = bucket.filter((e) => e.kind === '8-K').length;
    const plannedSales = bucket.filter((e) => e.kind === 'planned-sale').length;
    if (insiderBuys) {
      markers.push({
        time: time as UTCTimestamp,
        position: 'belowBar',
        shape: 'arrowUp',
        color: MM.up,
        size: 1,
        text: insiderBuys > 1 ? `${insiderBuys} insider buys` : 'insider buy',
      });
    }
    if (insiderSells) {
      markers.push({
        time: time as UTCTimestamp,
        position: 'aboveBar',
        shape: 'arrowDown',
        color: MM.down,
        size: 1,
        text: insiderSells > 1 ? `${insiderSells} insider sells` : 'insider sell',
      });
    }
    if (plannedSales) {
      markers.push({
        time: time as UTCTimestamp,
        position: 'aboveBar',
        shape: 'circle',
        color: MM.down,
        size: 0.7,
        text: plannedSales > 1 ? `${plannedSales} planned sales (144)` : 'planned sale (144)',
      });
    }
    if (filings) {
      markers.push({
        time: time as UTCTimestamp,
        position: 'aboveBar',
        shape: 'square',
        color: MM.muted,
        size: 0.6,
        text: filings > 1 ? `${filings} 8-Ks` : '8-K',
      });
    }
  }
  const all = [...markers, ...futureMarkers].sort((a, z) => (a.time as number) - (z.time as number));
  return { markers: all, futureTimes: [...futureTimes].sort((a, z) => a - z) };
}

export function CandleChart({
  bars,
  events = [],
  evidence = [],
  height = 380,
  revenue,
}: {
  bars: Ohlcv[];
  events?: ChartEvent[];
  /** Full evidence rows backing the markers — clicking a marker day pops their details. */
  evidence?: EvidenceItem[];
  height?: number;
  /** Quarterly revenue overlay (step line, own hidden scale). Omit/empty = hidden. */
  revenue?: RevenuePoint[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const revenueRef = useRef<ISeriesApi<'Line'> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const [dayPopup, setDayPopup] = useState<DayPopupState | null>(null);
  // Refs so the (once-subscribed) chart click handler always sees current data.
  const evidenceRef = useRef<EvidenceItem[]>(evidence);
  const barsRef = useRef<Ohlcv[]>(bars);
  evidenceRef.current = evidence;
  barsRef.current = bars;
  // TradingView muscle memory: right-click the price axis to flip log/linear. Persisted.
  const [logScale, setLogScale] = useState(() => {
    try {
      return localStorage.getItem('mm-log-scale') === '1';
    } catch {
      return false;
    }
  });

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
    // Quarterly revenue: step line with point markers on its own scale so dollar
    // magnitudes never distort the price axis. Band sits in the middle, clear of
    // the volume strip at the bottom.
    const revenueSeries = chart.addSeries(LineSeries, {
      priceScaleId: 'revenue',
      color: '#8fb8e8',
      lineWidth: 2,
      lineType: LineType.WithSteps,
      pointMarkersVisible: true,
      lastValueVisible: false,
      priceLineVisible: false,
      crosshairMarkerVisible: true,
      priceFormat: { type: 'custom', formatter: formatRevenue, minMove: 1 },
    });
    chart.priceScale('revenue').applyOptions({ scaleMargins: { top: 0.45, bottom: 0.2 }, visible: false });
    const markers = createSeriesMarkers(candle, []);

    // Click a marker day → popup with everything that hit that day (who, $, filing link).
    chart.subscribeClick((param) => {
      if (param.time == null || !param.point) {
        setDayPopup(null);
        return;
      }
      const time = param.time as number;
      const items = evidenceForDay(evidenceRef.current, normalize(barsRef.current), time);
      if (!items.length) {
        setDayPopup(null);
        return;
      }
      setDayPopup({ x: param.point.x, y: param.point.y, time, items });
    });

    chartRef.current = chart;
    candleRef.current = candle;
    volumeRef.current = volume;
    revenueRef.current = revenueSeries;
    markersRef.current = markers;

    const ro = new ResizeObserver(() => {
      if (containerRef.current) chart.applyOptions({ width: containerRef.current.clientWidth });
    });
    ro.observe(el);
    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      candleRef.current = null;
      volumeRef.current = null;
      revenueRef.current = null;
      markersRef.current = null;
    };
  }, [height]);

  // price-scale mode (runs after creation; also re-applies when the chart is rebuilt on height change)
  useEffect(() => {
    chartRef.current?.priceScale('right').applyOptions({ mode: logScale ? PriceScaleMode.Logarithmic : PriceScaleMode.Normal });
    try {
      localStorage.setItem('mm-log-scale', logScale ? '1' : '0');
    } catch {
      /* private mode — preference just doesn't persist */
    }
  }, [logScale, height]);

  // update data
  useEffect(() => {
    const candle = candleRef.current;
    const volume = volumeRef.current;
    const chart = chartRef.current;
    if (!candle || !volume || !chart) return;
    const rows = normalize(bars);
    const { markers, futureTimes } = decorationsFor(events, rows);
    // Whitespace points extend the time scale past the last candle so future-dated
    // planned-sale markers have a coordinate to land on.
    candle.setData([
      ...rows.map((b) => ({ time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c })),
      ...futureTimes.map((t) => ({ time: t as UTCTimestamp })),
    ]);
    volume.setData(
      rows.map((b) => ({ time: b.t as UTCTimestamp, value: b.v, color: b.c >= b.o ? 'rgba(105,197,137,.3)' : 'rgba(217,109,95,.3)' })),
    );
    const revenuePoints = [...(revenue ?? [])]
      .filter((p) => Number.isFinite(p.t) && Number.isFinite(p.value))
      .sort((a, z) => a.t - z.t);
    revenueRef.current?.setData(revenuePoints.map((p) => ({ time: p.t as UTCTimestamp, value: p.value })));
    chart.timeScale().fitContent();
    markersRef.current?.setMarkers(markers);
  }, [bars, events, revenue]);

  const onContextMenu = (event: React.MouseEvent<HTMLDivElement>) => {
    const chart = chartRef.current;
    const el = containerRef.current;
    if (!chart || !el) return;
    const rect = el.getBoundingClientRect();
    // Only when the right-click lands ON the price axis (same gesture as TradingView).
    const axisWidth = chart.priceScale('right').width();
    if (event.clientX >= rect.right - axisWidth) {
      event.preventDefault();
      setLogScale((v) => !v);
    }
  };

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
    <div style={{ position: 'relative' }} onContextMenu={onContextMenu}>
      <div ref={containerRef} style={{ width: '100%' }} />
      {dayPopup && (
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
              SEC activity · {evidenceDate(dayPopup.time)}
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
                  {item.value != null && <span style={{ fontFamily: mono, fontSize: 10.5, color: toneColor(item.tone), marginLeft: 6 }}>{formatMoney(item.value)}</span>}
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
      {logScale && (
        <span
          title="Logarithmic price scale — right-click the price axis to switch back to linear"
          style={{ position: 'absolute', top: 6, right: 6, zIndex: 5, borderRadius: 6, padding: '2px 7px', font: '700 8.5px Inter', letterSpacing: '.1em', background: 'rgba(251,148,35,.14)', color: MM.accent, border: `1px solid rgba(251,148,35,.3)`, pointerEvents: 'none' }}
        >
          LOG
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
