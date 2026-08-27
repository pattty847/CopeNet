import { LineSeries, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts';
import type { ChartComparisonLine } from './chartComparison';

export function replaceComparisonSeries(
  chart: IChartApi,
  existing: ISeriesApi<'Line'>[],
  lines: ChartComparisonLine[],
): ISeriesApi<'Line'>[] {
  existing.forEach((series) => chart.removeSeries(series));
  return lines.map((line) => {
    const series = chart.addSeries(LineSeries, {
      priceScaleId: 'right',
      color: line.color,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      priceFormat: {
        type: 'custom',
        minMove: 0.01,
        formatter: (value: number) => `${value > 0 ? '+' : ''}${value.toFixed(1)}%`,
      },
    });
    series.setData(line.data.map((point) => ({ time: point.t as UTCTimestamp, value: point.value })));
    return series;
  });
}
