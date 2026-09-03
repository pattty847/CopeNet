import { useEffect, useRef, type MutableRefObject } from 'react';
import { LineStyle, type ISeriesApi } from 'lightweight-charts';
import type { PriceAlert } from './types';
import { MM } from './marketUi';

type PriceLine = ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>;

export function useChartPriceAlertLines(
  candleRef: MutableRefObject<ISeriesApi<'Candlestick'> | null>,
  alerts: PriceAlert[],
  chartGeneration: number,
  draftPrice?: number | null,
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
      title: `Alert ${alert.direction === 'above' ? '>' : '<'}`,
    }));
    if (draftPrice != null && Number.isFinite(draftPrice) && draftPrice > 0) {
      linesRef.current.push(candle.createPriceLine({
        price: draftPrice,
        color: '#8fb8e8',
        lineWidth: 1,
        lineStyle: LineStyle.Solid,
        axisLabelVisible: true,
        title: 'New alert',
      }));
    }
    return () => {
      linesRef.current.forEach((line) => candle.removePriceLine(line));
      linesRef.current = [];
    };
  }, [alerts, candleRef, chartGeneration, draftPrice]);
}
