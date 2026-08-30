// Interval and range vocabulary, shared by the toolbar, the keyboard map, and the bar filter.
// Centralised because three surfaces disagreeing about what "3Y" means is a real bug class.

export type ChartTimeframe = 'D' | 'W' | 'M';
export type ChartRange = '6M' | '1Y' | '3Y' | '5Y' | 'MAX';

export const CHART_TIMEFRAMES: ChartTimeframe[] = ['D', 'W', 'M'];
export const CHART_RANGES: ChartRange[] = ['6M', '1Y', '3Y', '5Y', 'MAX'];

const RANGE_SECONDS: Record<Exclude<ChartRange, 'MAX'>, number> = {
  '6M': 183 * 86400,
  '1Y': 366 * 86400,
  '3Y': 3 * 366 * 86400,
  '5Y': 5 * 366 * 86400,
};

export function visibleBars<T extends { t: number }>(bars: T[], range: ChartRange): T[] {
  if (range === 'MAX' || bars.length === 0) return bars;
  const cutoff = bars[bars.length - 1].t - RANGE_SECONDS[range];
  return bars.filter((bar) => bar.t >= cutoff);
}

export function timeframeLabel(timeframe: ChartTimeframe): string {
  return timeframe === 'D' ? 'Daily' : timeframe === 'M' ? 'Monthly' : 'Weekly';
}

/** How Form 4 transactions are scoped and drawn on the chart. These outlived the popover
 *  component they were declared in; they belong with the chart's vocabulary. */
export type InsiderLookback = 'chart' | '90D' | '1Y' | '3Y' | '5Y' | 'MAX';
export type InsiderDisplayMode = 'individual' | 'clusters';
