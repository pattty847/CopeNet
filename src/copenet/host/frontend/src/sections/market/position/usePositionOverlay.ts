import { useEffect, type RefObject } from 'react';
import { createSeriesMarkers, LineStyle, type IChartApi, type ISeriesApi, type MouseEventParams } from 'lightweight-charts';
import { usePositionContext } from './PositionContext';
import { fillMarkers } from './model';
import { PositionPrimitive } from './primitive';

export function usePositionOverlay(chartRef: RefObject<IChartApi | null>, candleRef: RefObject<ISeriesApi<'Candlestick'> | null>, generation: number) {
  const context = usePositionContext();
  const position = context?.state.data?.position;
  const fills = context?.state.data?.fills;
  const preferences = context?.preferences;
  const hidden = context?.hidden ?? true;
  const bars = context?.bars;
  const timeframe = context?.timeframe;
  useEffect(() => {
    const candle = candleRef.current, chart = chartRef.current;
    if (!chart || !candle || !position || hidden || !preferences || !bars || !timeframe) return;
    const line = preferences.visible && position.avg_cost != null && position.avg_cost > 0 ? candle.createPriceLine({
      price: position.avg_cost, color: '#8fb8e8', lineWidth: 1, lineStyle: LineStyle.Dotted,
      axisLabelVisible: true, title: `AVG · ${position.quantity.toLocaleString()} shares`,
    }) : null;
    const primitive = new PositionPrimitive(position, preferences.shading);
    candle.attachPrimitive(primitive);
    const markers = preferences.fills ? createSeriesMarkers(candle, fillMarkers(fills ?? [], bars, timeframe), { autoScale: false }) : null;
    let alt = false;
    let hoveredPrice: number | null = null;
    const update = () => primitive.cursor(alt || preferences.cursor ? hoveredPrice : null);
    const key = (event: KeyboardEvent) => { alt = event.altKey; update(); };
    const blur = () => { alt = false; hoveredPrice = null; update(); };
    const move = (event: MouseEventParams) => {
      const pane = candle.getPane();
      hoveredPrice = event.point && (event.paneIndex == null || event.paneIndex === pane.paneIndex()) && event.point.y >= 0 && event.point.y < pane.getHeight()
        ? candle.coordinateToPrice(event.point.y) : null;
      update();
    };
    chart.subscribeCrosshairMove(move);
    window.addEventListener('keydown', key); window.addEventListener('keyup', key); window.addEventListener('blur', blur);
    return () => {
      window.removeEventListener('keydown', key); window.removeEventListener('keyup', key); window.removeEventListener('blur', blur);
      chart.unsubscribeCrosshairMove(move); markers?.detach(); candle.detachPrimitive(primitive);
      if (line) candle.removePriceLine(line);
    };
  }, [chartRef, candleRef, generation, position, preferences, hidden, bars, timeframe, fills]);
}
