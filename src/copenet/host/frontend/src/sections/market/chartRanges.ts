// Interval and range vocabulary, shared by the toolbar, the keyboard map, and the bar filter.
// Centralised because three surfaces disagreeing about what "3Y" means is a real bug class.

/** Sub-day intervals. Every one of these divides a native grain the backend fetches — the
 *  list mirrors `core/market/intraday/intervals.py` and the backend refuses anything else,
 *  so the two cannot silently disagree about what is offerable. */
export const INTRADAY_TIMEFRAMES = ['1m', '2m', '3m', '5m', '10m', '15m', '20m', '30m', '1h', '2h', '4h'] as const;
export type IntradayTimeframe = (typeof INTRADAY_TIMEFRAMES)[number];

export type DailyTimeframe = 'D' | 'W' | 'M';
export type ChartTimeframe = DailyTimeframe | IntradayTimeframe;

/** Which lane a timeframe reads from. Daily/weekly/monthly ride inside `ticker.detail`
 *  because they all derive from one cached daily history; intraday is a separate fetch. */
export function isIntradayTimeframe(timeframe: ChartTimeframe): timeframe is IntradayTimeframe {
  return (INTRADAY_TIMEFRAMES as readonly string[]).includes(timeframe);
}

export type DailyRange = '6M' | '1Y' | '3Y' | '5Y' | 'MAX';
/** Intraday windows top out at 60 days for 5m and 30 for 1m, so a "1Y" button on a 5m chart
 *  would be a control that cannot do anything. These are the ranges that exist there. */
export type IntradayRange = '1D' | '5D' | '1M' | 'MAX';
export type ChartRange = DailyRange | IntradayRange;

export const CHART_TIMEFRAMES: DailyTimeframe[] = ['D', 'W', 'M'];
export const CHART_RANGES: DailyRange[] = ['6M', '1Y', '3Y', '5Y', 'MAX'];
export const INTRADAY_RANGES: IntradayRange[] = ['1D', '5D', '1M', 'MAX'];

const RANGE_SECONDS: Record<Exclude<ChartRange, 'MAX'>, number> = {
  '1D': 86400,
  '5D': 5 * 86400,
  '1M': 31 * 86400,
  '6M': 183 * 86400,
  '1Y': 366 * 86400,
  '3Y': 3 * 366 * 86400,
  '5Y': 5 * 366 * 86400,
};

/** The ranges that make sense for a timeframe. Offering 5Y on a 5m chart is offering a
 *  button that produces the same 60 days as MAX and looks broken doing it. */
export function rangesFor(timeframe: ChartTimeframe): readonly ChartRange[] {
  return isIntradayTimeframe(timeframe) ? INTRADAY_RANGES : CHART_RANGES;
}

/** Keep the operator's range when switching lanes, or fall back to that lane's widest.
 *  Switching D to 5m with '5Y' selected would otherwise filter every bar away. */
export function rangeForTimeframe(range: ChartRange, timeframe: ChartTimeframe): ChartRange {
  const allowed = rangesFor(timeframe);
  return allowed.includes(range) ? range : 'MAX';
}

export function visibleBars<T extends { t: number }>(bars: T[], range: ChartRange): T[] {
  if (range === 'MAX' || bars.length === 0) return bars;
  const cutoff = bars[bars.length - 1].t - RANGE_SECONDS[range];
  return bars.filter((bar) => bar.t >= cutoff);
}

export function timeframeLabel(timeframe: ChartTimeframe): string {
  if (isIntradayTimeframe(timeframe)) {
    const value = Number.parseInt(timeframe, 10);
    return timeframe.endsWith('h') ? `${value} hour` : `${value} minute`;
  }
  return timeframe === 'D' ? 'Daily' : timeframe === 'M' ? 'Monthly' : 'Weekly';
}

/** How Form 4 transactions are scoped and drawn on the chart. These outlived the popover
 *  component they were declared in; they belong with the chart's vocabulary. */
export type InsiderLookback = 'chart' | '90D' | '1Y' | '3Y' | '5Y' | 'MAX';
export type InsiderDisplayMode = 'individual' | 'clusters';
