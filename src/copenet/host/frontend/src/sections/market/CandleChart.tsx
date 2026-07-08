// TradingView Lightweight Charts (v5) candlestick + volume, themed to CopeNet's dark palette.
// Consumes the typed OHLCV series from the ticker payload. Pure presentation — no data fetching.

import { useEffect, useRef } from 'react';
import {
  CandlestickSeries,
  ColorType,
  HistogramSeries,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
} from 'lightweight-charts';
import type { ChartEvent, Ohlcv } from './types';
import { MM } from './marketUi';

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
 *  nearest bar and drop events that fall outside the visible series entirely. */
function markersFor(events: ChartEvent[], bars: Ohlcv[]): SeriesMarker<Time>[] {
  if (!events.length || !bars.length) return [];
  const times = bars.map((b) => b.t);
  const grouped = new Map<number, ChartEvent[]>();
  for (const event of events) {
    if (!Number.isFinite(event.t)) continue;
    let nearest = times[0];
    let bestDiff = Math.abs(times[0] - event.t);
    for (const t of times) {
      const diff = Math.abs(t - event.t);
      if (diff < bestDiff) {
        nearest = t;
        bestDiff = diff;
      }
    }
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
  return markers.sort((a, z) => (a.time as number) - (z.time as number));
}

export function CandleChart({ bars, events = [], height = 380 }: { bars: Ohlcv[]; events?: ChartEvent[]; height?: number }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

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
    const markers = createSeriesMarkers(candle, []);

    chartRef.current = chart;
    candleRef.current = candle;
    volumeRef.current = volume;
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
      markersRef.current = null;
    };
  }, [height]);

  // update data
  useEffect(() => {
    const candle = candleRef.current;
    const volume = volumeRef.current;
    const chart = chartRef.current;
    if (!candle || !volume || !chart) return;
    const rows = normalize(bars);
    candle.setData(rows.map((b) => ({ time: b.t as UTCTimestamp, open: b.o, high: b.h, low: b.l, close: b.c })));
    volume.setData(
      rows.map((b) => ({ time: b.t as UTCTimestamp, value: b.v, color: b.c >= b.o ? 'rgba(105,197,137,.3)' : 'rgba(217,109,95,.3)' })),
    );
    chart.timeScale().fitContent();
    markersRef.current?.setMarkers(markersFor(events, rows));
  }, [bars, events]);

  return (
    <div style={{ position: 'relative' }}>
      <div ref={containerRef} style={{ width: '100%' }} />
      {bars.length === 0 && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: MM.dim, fontSize: 12, fontStyle: 'italic', pointerEvents: 'none' }}>
          Loading candles…
        </div>
      )}
    </div>
  );
}
