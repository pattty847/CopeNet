import { useEffect, useRef, type RefObject } from 'react';
import type { IChartApi, ISeriesApi } from 'lightweight-charts';
import type { ChartAnchor, ChartObject, ChartViewport } from '../chartAgent/types';
import { leftAxisWidth } from '../chartDecorations';
import { anchorIndexAt, hitDrawing, replaceAnchor } from './geometry';
import { DrawingPrimitive } from './primitive';
import type { ChartWorkspaceBridge } from './types';

export function readChartViewport(chart: IChartApi, candle: ISeriesApi<'Candlestick'>): ChartViewport {
  const logical = chart.timeScale().getVisibleLogicalRange();
  if (!logical) return { from: null, to: null, logicalFrom: null, logicalTo: null };
  // Include partly visible edge candles. Index lookup follows the shared chart timeline,
  // including whitespace introduced by future SEC markers; it does not invent timestamps.
  const first = candle.dataByIndex(Math.floor(logical.from), 1);
  const last = candle.dataByIndex(Math.ceil(logical.to), -1);
  let from = first?.time;
  let to = last?.time;
  // Future SEC markers extend the shared time axis using whitespace. It must remain
  // logical whitespace in capture, never an invented candle at its endpoint.
  if ((first && !('close' in first)) || (last && !('close' in last))) {
    const rows = candle.data().filter((row) => 'close' in row && typeof row.time === 'number' &&
      typeof from === 'number' && typeof to === 'number' && row.time >= from && row.time <= to);
    from = rows[0]?.time;
    to = rows[rows.length - 1]?.time;
  }
  return {
    from: typeof from === 'number' ? from : null,
    to: typeof to === 'number' ? to : null,
    logicalFrom: logical.from,
    logicalTo: logical.to,
  };
}

export function useChartWorkspace(
  chartRef: RefObject<IChartApi | null>,
  candleRef: RefObject<ISeriesApi<'Candlestick'> | null>,
  containerRef: RefObject<HTMLDivElement | null>,
  generation: number,
  bridge: ChartWorkspaceBridge | undefined,
  comparisonMode: boolean,
): void {
  const current = useRef({ bridge, comparisonMode });
  current.current = { bridge, comparisonMode };
  const primitiveRef = useRef<DrawingPrimitive | null>(null);
  const resetGesture = useRef<(() => void) | null>(null);

  useEffect(() => {
    const chart = chartRef.current;
    const candle = candleRef.current;
    const container = containerRef.current;
    if (!chart || !candle || !container) return;
    const primitive = new DrawingPrimitive(() => container.getClientRects().length > 0 && container.clientWidth > 0 && container.clientHeight > 0);
    primitiveRef.current = primitive;
    candle.attachPrimitive(primitive);
    primitive.setState(current.current.bridge, current.current.comparisonMode);
    let first: ChartAnchor | null = null;
    let drag: { object: ChartObject; index: number; anchor: ChartAnchor; revision: number } | null = null;
    let ownsPointer = false;
    let pointerId: number | null = null;
    let viewportKey = '';

    const publishViewport = () => {
      const active = current.current.bridge;
      if (!active) return;
      const viewport = readChartViewport(chart, candle);
      const key = `${active.documentId}:${active.timeframe}:${JSON.stringify(viewport)}`;
      if (key !== viewportKey) { viewportKey = key; active.onViewport(viewport); }
    };
    const clear = () => {
      first = null;
      drag = null;
      ownsPointer = false;
      primitive.setPreview(null);
      if (pointerId !== null && container.hasPointerCapture(pointerId)) container.releasePointerCapture(pointerId);
      pointerId = null;
    };
    resetGesture.current = clear;
    const pointFromEvent = (event: PointerEvent) => {
      const bounds = container.getBoundingClientRect();
      return { x: event.clientX - bounds.left - leftAxisWidth(chart), y: event.clientY - bounds.top };
    };
    const anchorAt = (point: { x: number; y: number }): ChartAnchor | null => {
      const pane = chart.paneSize(0);
      if (point.x < 0 || point.x > pane.width || point.y < 0 || point.y > pane.height) return null;
      const time = chart.timeScale().coordinateToTime(point.x);
      const value = candle.coordinateToPrice(point.y);
      if (typeof time !== 'number' || value == null || !Number.isFinite(value) || value <= 0) return null;
      // Whitespace can have a chart timestamp but no candle; those are not valid anchors.
      const logical = chart.timeScale().coordinateToLogical(point.x);
      const row = logical == null ? null : candle.dataByIndex(Math.round(logical));
      return row && 'close' in row ? { t: time, value } : null;
    };
    const preview = (active: ChartWorkspaceBridge, anchors: ChartAnchor[]) => {
      if (active.mode === 'select' || active.mode === 'range') return;
      primitive.setPreview({ id: '__preview', kind: active.mode, anchors, timeframe: active.timeframe,
        color: '#fb9423', label: '', rationale: '', evidence: [], owner: { kind: 'operator' }, visible: true });
    };
    const onDown = (event: PointerEvent) => {
      const active = current.current.bridge;
      if (!active?.enabled || active.interactionEnabled === false || current.current.comparisonMode || event.button !== 0) return;
      const point = pointFromEvent(event);
      const anchor = anchorAt(point);
      if (!anchor) return;
      if (active.mode === 'select') {
        const hit = [...primitive.geometries()].reverse().find((geometry) => geometry.object.id !== '__preview' && hitDrawing(geometry, point));
        if (!hit) { active.onSelectObject(null); return; }
        const index = anchorIndexAt(hit, point);
        if (hit.object.id === active.selectedObjectId && index >= 0) drag = { object: hit.object, index, anchor, revision: active.revision };
        active.onSelectObject(hit.object.id);
      }
      ownsPointer = true;
      pointerId = event.pointerId;
      container.setPointerCapture(event.pointerId);
      event.preventDefault();
      event.stopImmediatePropagation();
    };
    const onMove = (event: PointerEvent) => {
      const active = current.current.bridge;
      if (!active?.enabled || active.interactionEnabled === false || current.current.comparisonMode) return;
      const anchor = anchorAt(pointFromEvent(event));
      if (!anchor) return;
      if (drag) {
        drag.anchor = anchor;
        primitive.setPreview({ ...drag.object, id: '__preview', anchors: replaceAnchor(drag.object.anchors, drag.index, anchor) });
        event.preventDefault();
        event.stopImmediatePropagation();
      } else if (first) preview(active, [first, anchor]);
    };
    const onUp = (event: PointerEvent) => {
      if (!ownsPointer) return;
      const active = current.current.bridge;
      const anchor = anchorAt(pointFromEvent(event));
      ownsPointer = false;
      if (container.hasPointerCapture(event.pointerId)) container.releasePointerCapture(event.pointerId);
      pointerId = null;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!active || !anchor) { clear(); return; }
      if (drag) {
        if (active.revision !== drag.revision) { clear(); return; }
        active.onUpdate({ id: drag.object.id, anchors: replaceAnchor(drag.object.anchors, drag.index, drag.anchor) });
        clear();
      } else if (active.mode === 'range') {
        if (!first) {
          first = anchor;
          primitive.setPreview({ id: '__preview', kind: 'label', anchors: [anchor], timeframe: active.timeframe,
            color: '#fb9423', label: 'Choose end candle · Esc cancels', rationale: '', evidence: [], owner: { kind: 'operator' }, visible: true });
        }
        else { active.onSelectRange({ from: Math.min(first.t, anchor.t), to: Math.max(first.t, anchor.t) }); clear(); }
      } else if (active.mode === 'level' || active.mode === 'label') {
        active.onCreate({ kind: active.mode, anchors: [anchor], timeframe: active.timeframe }); clear();
      } else if (active.mode === 'zone' || active.mode === 'trendline') {
        if (!first) { first = anchor; preview(active, [anchor, anchor]); }
        else if (first.t !== anchor.t) { active.onCreate({ kind: active.mode, anchors: [first, anchor], timeframe: active.timeframe }); clear(); }
      }
    };
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape') clear(); };
    const onVisibility = () => { if (document.visibilityState === 'visible') { primitive.setState(current.current.bridge, current.current.comparisonMode); publishViewport(); } };
    chart.timeScale().subscribeVisibleLogicalRangeChange(publishViewport);
    container.addEventListener('pointerdown', onDown, true);
    container.addEventListener('pointermove', onMove, true);
    container.addEventListener('pointerup', onUp, true);
    container.addEventListener('pointercancel', clear, true);
    window.addEventListener('keydown', onKey);
    document.addEventListener('visibilitychange', onVisibility);
    const frame = requestAnimationFrame(publishViewport);
    return () => {
      clear();
      resetGesture.current = null;
      cancelAnimationFrame(frame);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(publishViewport);
      container.removeEventListener('pointerdown', onDown, true);
      container.removeEventListener('pointermove', onMove, true);
      container.removeEventListener('pointerup', onUp, true);
      container.removeEventListener('pointercancel', clear, true);
      window.removeEventListener('keydown', onKey);
      document.removeEventListener('visibilitychange', onVisibility);
      // The owning chart may already have been removed during React's unmount cleanup.
      if (chartRef.current === chart) candle.detachPrimitive(primitive);
      primitive.detached();
      primitiveRef.current = null;
    };
  }, [chartRef, candleRef, containerRef, generation]);

  useEffect(() => {
    primitiveRef.current?.setState(bridge, comparisonMode);
  }, [bridge, comparisonMode]);

  useEffect(() => {
    const chart = chartRef.current;
    const candle = candleRef.current;
    if (chart && candle && current.current.bridge) current.current.bridge.onViewport(readChartViewport(chart, candle));
  }, [chartRef, candleRef, bridge?.documentId, bridge?.timeframe]);

  useEffect(() => { resetGesture.current?.(); }, [bridge?.documentId, bridge?.revision, bridge?.timeframe, bridge?.mode, bridge?.enabled, bridge?.interactionEnabled, comparisonMode]);
}
