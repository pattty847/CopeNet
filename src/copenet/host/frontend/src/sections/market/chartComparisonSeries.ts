import { LineSeries, LineStyle, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts';
import type { ChartComparisonLine } from './chartComparison';
import type { LineStyle as LineStyleName } from './chartStyle/types';

export function replaceComparisonSeries(
  chart: IChartApi,
  existing: ISeriesApi<'Line'>[],
  lines: ChartComparisonLine[],
  stroke: { width: number; style: LineStyleName } = { width: 2, style: 'solid' },
): ISeriesApi<'Line'>[] {
  existing.forEach((series) => chart.removeSeries(series));
  return lines.map((line) => {
    const series = chart.addSeries(LineSeries, {
      priceScaleId: 'right',
      color: line.color,
      lineWidth: stroke.width as 1 | 2 | 3 | 4,
      lineStyle: stroke.style === 'dashed' ? LineStyle.Dashed : stroke.style === 'dotted' ? LineStyle.Dotted : LineStyle.Solid,
      priceLineVisible: false,
      lastValueVisible: true,
      crosshairMarkerVisible: true,
      priceFormat: {
        type: 'custom',
        minMove: 0.01,
        formatter: (value: number) => line.valueMode === 'percent'
          ? `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
          : value.toLocaleString(undefined, { maximumFractionDigits: 4 }),
      },
    });
    series.setData(line.data.map((point) => ({ time: point.t as UTCTimestamp, value: point.value })));
    return series;
  });
}
