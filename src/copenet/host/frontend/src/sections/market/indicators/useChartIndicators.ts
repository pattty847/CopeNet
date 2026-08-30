// The one seam between React and the indicator chart layer.
//
// `CandleChart` calls this and nothing else. Keeping the whole subsystem behind a single hook
// is what stops the chart component from growing an indicator manager: it never sees a pane,
// a series, or a definition — only a list of rectangles it can hang controls on.

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import type { IChartApi } from 'lightweight-charts';
import type { ComputedIndicator } from './compute';
import { IndicatorChartLayer } from './render';

/** Where one indicator's PLOT AREA sits, in coordinates relative to the chart wrapper.
 *
 *  Deliberately the plot area and not the pane element. The pane spans the full chart width
 *  including its price scale, so right-aligning controls to it puts them on top of the axis
 *  labels — visible in the DOM, unreadable on screen. `left`/`width` therefore describe the
 *  canvas; `top`/`height` still describe the pane. */
export interface IndicatorPaneRect {
  instanceId: string;
  left: number;
  top: number;
  height: number;
  width: number;
}

export function useChartIndicators(
  chartRef: RefObject<IChartApi | null>,
  /** Bumped whenever the chart itself is rebuilt, which invalidates every series handle. */
  chartGeneration: number,
  indicators: ComputedIndicator[],
  /** The positioned wrapper pane controls are placed against. */
  containerRef: RefObject<HTMLElement | null>,
  /** Stretch factor for the price pane; each indicator carries its own. */
  priceStretch: number,
  /** Called when the operator finishes dragging a pane separator, so the new division can be
   *  persisted. Never called for a division this hook applied itself. */
  onPaneStretchChange?: (next: { priceStretch: number; byInstance: Record<string, number> }) => void,
): IndicatorPaneRect[] {
  const layerRef = useRef<IndicatorChartLayer | null>(null);
  const [paneRects, setPaneRects] = useState<IndicatorPaneRect[]>([]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;
    const layer = new IndicatorChartLayer(chart);
    layerRef.current = layer;
    return () => {
      // The chart may already be disposed by the time this runs — the component's own
      // teardown calls chart.remove() first. Every call inside destroy() is guarded, so the
      // ordering does not matter and the layer's own bookkeeping is cleared either way.
      layer.destroy();
      layerRef.current = null;
      setPaneRects([]);
    };
    // chartRef is a ref and never changes identity; the generation is the real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartGeneration]);

  const measure = useCallback(() => {
    const layer = layerRef.current;
    const container = containerRef.current;
    if (!layer || !container) return;
    const origin = container.getBoundingClientRect();
    const next = layer.paneElements().map(({ instanceId, element }) => {
      const box = element.getBoundingClientRect();
      const plot = plotArea(element) ?? box;
      return {
        instanceId,
        left: plot.left - origin.left,
        top: box.top - origin.top,
        height: box.height,
        width: plot.width,
      };
    });
    // Replace only on a real change. This runs from a ResizeObserver, and setting a fresh
    // array every callback would re-render the overlay on every frame of a pane drag.
    setPaneRects((current) => (sameRects(current, next) ? current : next));
  }, [containerRef]);

  useEffect(() => {
    layerRef.current?.sync(indicators, priceStretch);
    measure();
  }, [indicators, chartGeneration, measure, priceStretch]);

  // Pointer interaction on the chart is where BOTH of these are settled, and neither has an
  // event of its own: Lightweight Charts publishes nothing for a price-scale change or a
  // pane-separator drag.
  //
  //  * A bounded scale is re-asserted on every move, so an accidental drag on an RSI axis
  //    cannot leave its declared 0-100 quietly switched off. The scale reads as locked,
  //    which is what a declared range means.
  //  * A separator drag is read back on release and handed up to be persisted.
  const stretchRef = useRef(onPaneStretchChange);
  stretchRef.current = onPaneStretchChange;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const hold = () => layerRef.current?.enforceBoundedScales();
    const settle = () => {
      const layer = layerRef.current;
      if (!layer) return;
      layer.enforceBoundedScales();
      const next = layer.readPaneStretch();
      if (Object.keys(next.byInstance).length) stretchRef.current?.(next);
    };
    container.addEventListener('pointermove', hold, { passive: true });
    container.addEventListener('wheel', hold, { passive: true });
    container.addEventListener('pointerup', settle, { passive: true });
    container.addEventListener('pointerleave', settle, { passive: true });
    return () => {
      container.removeEventListener('pointermove', hold);
      container.removeEventListener('wheel', hold);
      container.removeEventListener('pointerup', settle);
      container.removeEventListener('pointerleave', settle);
    };
  }, [containerRef, chartGeneration]);

  // Observe each pane element directly rather than sampling on an animation frame.
  //
  // Dragging a pane separator publishes no event, but it does resize the panes either side
  // of it — and a pane above resizing moves every pane below it, whose own observers then
  // fire too. So observing the elements covers separator drags, chart resizes and pane
  // add/remove with no polling at all.
  useEffect(() => {
    const container = containerRef.current;
    const layer = layerRef.current;
    if (!container || !layer) return;
    const observer = new ResizeObserver(measure);
    observer.observe(container);
    for (const { element } of layer.paneElements()) observer.observe(element);
    measure();
    return () => observer.disconnect();
  }, [containerRef, indicators, chartGeneration, measure]);

  return paneRects;
}

/** The pane's drawing surface, as distinct from the pane row that also holds its price
 *  scales. Identified as the WIDEST canvas inside the pane rather than by position, so it
 *  does not depend on how Lightweight Charts orders or nests its layers — and it stays
 *  correct when a left-hand axis appears for a financial overlay. */
function plotArea(paneElement: HTMLElement): DOMRect | null {
  let widest: DOMRect | null = null;
  for (const canvas of paneElement.querySelectorAll('canvas')) {
    const rect = canvas.getBoundingClientRect();
    if (!widest || rect.width > widest.width) widest = rect;
  }
  return widest;
}

function sameRects(left: IndicatorPaneRect[], right: IndicatorPaneRect[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((rect, i) => {
    const other = right[i];
    return rect.instanceId === other.instanceId
      && Math.abs(rect.left - other.left) < 0.5
      && Math.abs(rect.top - other.top) < 0.5
      && Math.abs(rect.height - other.height) < 0.5
      && Math.abs(rect.width - other.width) < 0.5;
  });
}
