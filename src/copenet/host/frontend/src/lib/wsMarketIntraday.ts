import type { IntradayCatalog, IntradaySeries } from '../types/backend';
import type { ChartTimeframe } from '../sections/market/chartRanges';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function optionalNumber(value: unknown): number | null {
  return value == null ? null : Number(value);
}

function normalizeSeries(raw: unknown): IntradaySeries {
  const value = asRecord(raw);
  const rows = Array.isArray(value.bars) ? value.bars : [];
  return {
    symbol: String(value.symbol || ''),
    interval: String(value.interval || '') as ChartTimeframe,
    session: String(value.session || 'all') as IntradaySeries['session'],
    grain: String(value.grain || ''),
    windowDays: Number(value.windowDays) || 0,
    bars: rows.map((entry) => {
      const bar = asRecord(entry);
      return {
        t: Number(bar.t) || 0,
        o: Number(bar.o) || 0,
        h: Number(bar.h) || 0,
        l: Number(bar.l) || 0,
        c: Number(bar.c) || 0,
        // Overnight bars report no volume. Zero is the measurement, not a missing field.
        v: Number(bar.v) || 0,
      };
    }),
    coveredFrom: optionalNumber(value.coveredFrom),
    coveredThrough: optionalNumber(value.coveredThrough),
    fetched: Boolean(value.fetched),
    requests: Number(value.requests) || 0,
    warnings: Array.isArray(value.warnings) ? value.warnings.map(String) : [],
    unavailable: value.unavailable == null ? null : String(value.unavailable),
    updatedAt: String(value.updatedAt || ''),
  };
}

export async function marketIntradayGetRpc(
  request: WsRpcRequest,
  options: { symbol: string; interval: string; session?: string; days?: number; refresh?: boolean },
): Promise<IntradaySeries> {
  const payload = await request<Record<string, unknown>>('market.intraday.get', {
    symbol: options.symbol,
    interval: options.interval,
    session: options.session ?? 'all',
    ...(options.days ? { days: options.days } : {}),
    ...(options.refresh ? { refresh: true } : {}),
  });
  return normalizeSeries(payload);
}

/** The offerable intervals and their real depth, sent by the backend rather than hardcoded
 *  here so the selector cannot drift from what the fetch lane can actually serve. */
export async function marketIntradayIntervalsRpc(request: WsRpcRequest): Promise<IntradayCatalog> {
  const payload = await request<{ intervals?: unknown; sessions?: unknown }>('market.intraday.intervals', {});
  const rows = Array.isArray(payload.intervals) ? payload.intervals : [];
  return {
    intervals: rows.map((entry) => {
      const row = asRecord(entry);
      return {
        interval: String(row.interval || '') as ChartTimeframe,
        grain: String(row.grain || ''),
        derived: Boolean(row.derived),
        windowDays: Number(row.windowDays) || 0,
        paged: Boolean(row.paged),
      };
    }),
    sessions: Array.isArray(payload.sessions) ? payload.sessions.map(String) : ['all', 'regular', 'extended'],
  };
}
