// The one seam between React and the indicator chart layer.
//
// `CandleChart` calls this and nothing else. Keeping the whole subsystem behind a single hook
// is what stops the chart component from growing an indicator manager: it never sees a pane,
// a series, or a definition.

import { useEffect, useRef, type RefObject } from 'react';
import type { IChartApi } from 'lightweight-charts';
import type { ComputedIndicator } from './compute';
import { IndicatorChartLayer } from './render';

export function useChartIndicators(
  chartRef: RefObject<IChartApi | null>,
  /** Bumped whenever the chart itself is rebuilt, which invalidates every series handle. */
  chartGeneration: number,
  indicators: ComputedIndicator[],
): void {
  const layerRef = useRef<IndicatorChartLayer | null>(null);

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
    };
    // chartRef is a ref and never changes identity; the generation is the real dependency.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartGeneration]);

  useEffect(() => {
    layerRef.current?.sync(indicators);
  }, [indicators, chartGeneration]);
}
