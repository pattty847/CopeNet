import { useEffect, useRef, type MutableRefObject } from 'react';
import { LineStyle, type ISeriesApi } from 'lightweight-charts';
import type { PriceAlert } from './types';
import { MM } from './marketUi';

type PriceLine = ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>;

export function useChartPriceAlertLines(
  candleRef: MutableRefObject<ISeriesApi<'Candlestick'> | null>,
  alerts: PriceAlert[],
  chartGeneration: number,
) {
  const linesRef = useRef<PriceLine[]>([]);

  useEffect(() => {
    const candle = candleRef.current;
    if (!candle) return;
    linesRef.current.forEach((line) => candle.removePriceLine(line));
    linesRef.current = alerts.map((alert) => candle.createPriceLine({
      price: alert.threshold,
      color: MM.accent,
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      axisLabelVisible: true,
      title: `Alert ${alert.direction === 'above' ? '≥' : '≤'}`,
    }));
    return () => {
      linesRef.current.forEach((line) => candle.removePriceLine(line));
      linesRef.current = [];
    };
  }, [alerts, candleRef, chartGeneration]);
}
