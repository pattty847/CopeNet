import type { SeriesMarker, UTCTimestamp } from 'lightweight-charts';
import type { Ohlcv } from '../types';
import type { HeldPosition, PositionFill, PositionPreferences } from './types';
import { isIntradayTimeframe, type ChartTimeframe } from '../chartRanges';
import { MM } from '../marketUi';

export const DEFAULT_POSITION_PREFERENCES: PositionPreferences = { visible: true, shading: false, fills: false, cursor: false };
export function loadPositionPreferences(): PositionPreferences {
  try {
    const saved = JSON.parse(localStorage.getItem('mm-position-display') ?? '{}');
    return Object.fromEntries(Object.entries(DEFAULT_POSITION_PREFERENCES).map(([key, fallback]) =>
      [key, typeof saved[key] === 'boolean' ? saved[key] : fallback])) as unknown as PositionPreferences;
  } catch { return DEFAULT_POSITION_PREFERENCES; }
}
export function money(value: number | null | undefined, currency: string | null = null): string {
  if (value == null) return '—';
  return currency ? new Intl.NumberFormat(undefined, { style: 'currency', currency, maximumFractionDigits: 2 }).format(value)
    : `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value)} (currency unknown)`;
}
export function percent(value: number | null | undefined): string {
  return value == null ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`;
}
export function scenario(position: HeldPosition, price: number): { dollars: number; percent: number } | null {
  if (position.avg_cost == null || position.avg_cost <= 0 || !Number.isFinite(price) || price <= 0) return null;
  const dollars = (price - position.avg_cost) * position.quantity;
  return { dollars, percent: dollars / (position.avg_cost * Math.abs(position.quantity)) * 100 };
}
/** Fills attach to existing candle slots only; their original execution prices never alter the price scale. */
export function fillMarkers(fills: PositionFill[], bars: Ohlcv[], timeframe: ChartTimeframe = 'D'): SeriesMarker<UTCTimestamp>[] {
  const intraday = isIntradayTimeframe(timeframe);
  const interval = intraday ? Number.parseInt(timeframe, 10) * (timeframe.endsWith('h') ? 3600 : 60) : 0;
  const groups = new Map<number, { buy: number; sell: number; short: number }>();
  for (const fill of fills) {
    const stamp = intraday ? Date.parse(fill.filledAt) / 1000 : Date.parse(`${fill.sessionDate}T00:00:00Z`) / 1000;
    // For D/W/M, bucket the session just as the candle cache does. Do not snap a missing
    // session or a future fill to the last visible candle.
    const date = new Date(stamp * 1000);
    if (!intraday && timeframe === 'W') date.setUTCDate(date.getUTCDate() - (date.getUTCDay() + 6) % 7);
    if (!intraday && timeframe === 'M') date.setUTCDate(1);
    const bucket = date.getTime() / 1000;
    let index = -1;
    if (intraday) {
      index = bars.findIndex((bar, i) => bar.t <= stamp && Math.min(bars[i + 1]?.t ?? Infinity, bar.t + interval) > stamp);
    } else index = bars.findIndex((bar) => bar.t === bucket);
    if (index < 0) continue;
    const group = groups.get(bars[index].t) ?? { buy: 0, sell: 0, short: 0 };
    if (fill.side === 'BUY') group.buy += 1;
    if (fill.side === 'SELL') group.sell += 1;
    if (fill.side === 'SHORT') group.short += 1;
    groups.set(bars[index].t, group);
  }
  return [...groups].sort(([a], [b]) => a - b).flatMap(([time, group]): SeriesMarker<UTCTimestamp>[] => [
    ...(group.buy ? [{ time: time as UTCTimestamp, position: 'belowBar' as const, shape: 'arrowUp' as const, color: MM.up, text: `Buy${group.buy > 1 ? ` ×${group.buy}` : ''}` }] : []),
    ...(group.short ? [{ time: time as UTCTimestamp, position: 'aboveBar' as const, shape: 'arrowDown' as const, color: MM.down, text: `Short${group.short > 1 ? ` ×${group.short}` : ''}` }] : []),
    ...(group.sell ? [{ time: time as UTCTimestamp, position: 'aboveBar' as const, shape: 'arrowDown' as const, color: MM.down, text: `Sell${group.sell > 1 ? ` ×${group.sell}` : ''}` }] : []),
  ]);
}
