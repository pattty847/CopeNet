// The one seam between React and the indicator chart layer.
//
// `CandleChart` calls this and nothing else. Keeping the whole subsystem behind a single hook
// is what stops the chart component from growing an indicator manager: it never sees a pane,
// a series, or a definition — only a list of rectangles it can hang controls on.

import { useCallback, useEffect, useRef, useState, type RefObject } from 'react';
import type { IChartApi } from 'lightweight-charts';
import type { ComputedIndicator } from './compute';
import { IndicatorChartLayer } from './render';

/** Where one indicator's pane sits, in coordinates relative to the chart wrapper. */
export interface IndicatorPaneRect {
  instanceId: string;
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
      return { instanceId, top: box.top - origin.top, height: box.height, width: box.width };
    });
    // Replace only on a real change. This runs from a ResizeObserver, and setting a fresh
    // array every callback would re-render the overlay on every frame of a pane drag.
    setPaneRects((current) => (sameRects(current, next) ? current : next));
  }, [containerRef]);

  useEffect(() => {
    layerRef.current?.sync(indicators);
    measure();
  }, [indicators, chartGeneration, measure]);

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

function sameRects(left: IndicatorPaneRect[], right: IndicatorPaneRect[]): boolean {
  if (left.length !== right.length) return false;
  return left.every((rect, i) => {
    const other = right[i];
    return rect.instanceId === other.instanceId
      && Math.abs(rect.top - other.top) < 0.5
      && Math.abs(rect.height - other.height) < 0.5
      && Math.abs(rect.width - other.width) < 0.5;
  });
}
