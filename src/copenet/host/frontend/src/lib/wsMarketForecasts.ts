import type { LedgerReport } from '../sections/market/types';
import type { ForecastChart, ForecastRecord, ForecastRenderReceipt, ForecastRequest } from '../sections/market/forecasts/types';

type Request = <T extends Record<string, unknown>>(method: string, params: Record<string, unknown>) => Promise<T>;
export function createMarketForecastApi(request: Request) {
  const listeners = new Set<() => void>();
  return {
    report: (filters: { forecastProvider?: string; forecastModel?: string; forecastFrom?: string; forecastTo?: string }) => request<LedgerReport & Record<string, unknown>>('market.ledger.get', { ...filters }),
    receive() { listeners.forEach((listener) => listener()); },
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    request: (params: ForecastRequest) => request<{ forecast: ForecastRecord }>('market.forecast.request', { ...params }),
    evidence: (forecastId: string, evidenceId: string) => request<{ evidence: Record<string, unknown> }>('market.forecast.get', { forecastId, evidenceId }),
    get: (forecastId: string) => request<{ forecast: ForecastRecord; chart: ForecastChart | null }>('market.forecast.get', { forecastId, includeChart: true }),
    list: (documentId?: string, offset = 0) => request<{ forecasts: ForecastRecord[]; nextOffset: number | null; offset: number }>('market.forecast.list', { documentId, offset, limit: 100 }),
    cancel: (forecastId: string) => request<{ forecast: ForecastRecord }>('market.forecast.cancel', { forecastId }),
    amend: (forecastId: string, expectedRevision: number, amendment: Record<string, unknown>) =>
      request<{ forecast: ForecastRecord }>('market.forecast.amend', { forecastId, expectedRevision, amendment }),
    tracking: (forecastId: string, scanId: string | null) => request<{ forecast: ForecastRecord }>('market.forecast.tracking.update', { forecastId, scanId }),
    rendered: (receipt: ForecastRenderReceipt) => request('market.forecast.rendered', { ...receipt }),
  };
}
