import type { InsiderDisplayMode, InsiderLookback } from './ChartEvidenceControl';
import type { ChartRange, ChartTimeframe } from './MarketChartToolbar';
import type { FinancialFrequency } from './types';

const STORAGE_KEY = 'copenet-market-ticker-chart-view';
const TIMEFRAMES = new Set<ChartTimeframe>(['D', 'W', 'M']);
const RANGES = new Set<ChartRange>(['6M', '1Y', '3Y', '5Y', 'MAX']);
const FREQUENCIES = new Set<FinancialFrequency>(['quarterly', 'annual', 'ttm']);
const LOOKBACKS = new Set<InsiderLookback>(['chart', '90D', '1Y', '3Y', '5Y', 'MAX']);
const DISPLAY_MODES = new Set<InsiderDisplayMode>(['individual', 'clusters']);

export interface TickerChartViewState {
  timeframe: ChartTimeframe;
  range: ChartRange;
  overlayMetric: string | null;
  overlayFrequency: FinancialFrequency;
  showInsiderTransactions: boolean;
  insiderLookback: InsiderLookback;
  insiderDisplayMode: InsiderDisplayMode;
}

export const DEFAULT_TICKER_CHART_VIEW: TickerChartViewState = {
  timeframe: 'W',
  range: '5Y',
  overlayMetric: null,
  overlayFrequency: 'quarterly',
  showInsiderTransactions: false,
  insiderLookback: 'chart',
  insiderDisplayMode: 'clusters',
};

export function readTickerChartViewState(storage: Pick<Storage, 'getItem'> | null = typeof window === 'undefined' ? null : window.sessionStorage): TickerChartViewState {
  if (!storage) return DEFAULT_TICKER_CHART_VIEW;
  try {
    const raw = JSON.parse(storage.getItem(STORAGE_KEY) ?? '{}') as Record<string, unknown>;
    return {
      timeframe: TIMEFRAMES.has(raw.timeframe as ChartTimeframe) ? raw.timeframe as ChartTimeframe : DEFAULT_TICKER_CHART_VIEW.timeframe,
      range: RANGES.has(raw.range as ChartRange) ? raw.range as ChartRange : DEFAULT_TICKER_CHART_VIEW.range,
      overlayMetric: typeof raw.overlayMetric === 'string' && raw.overlayMetric.length <= 80 ? raw.overlayMetric : null,
      overlayFrequency: FREQUENCIES.has(raw.overlayFrequency as FinancialFrequency) ? raw.overlayFrequency as FinancialFrequency : DEFAULT_TICKER_CHART_VIEW.overlayFrequency,
      showInsiderTransactions: raw.showInsiderTransactions === true,
      insiderLookback: LOOKBACKS.has(raw.insiderLookback as InsiderLookback) ? raw.insiderLookback as InsiderLookback : DEFAULT_TICKER_CHART_VIEW.insiderLookback,
      insiderDisplayMode: DISPLAY_MODES.has(raw.insiderDisplayMode as InsiderDisplayMode) ? raw.insiderDisplayMode as InsiderDisplayMode : DEFAULT_TICKER_CHART_VIEW.insiderDisplayMode,
    };
  } catch {
    return DEFAULT_TICKER_CHART_VIEW;
  }
}

export function writeTickerChartViewState(state: TickerChartViewState, storage: Pick<Storage, 'setItem'> | null = typeof window === 'undefined' ? null : window.sessionStorage): void {
  if (!storage) return;
  try { storage.setItem(STORAGE_KEY, JSON.stringify(state)); } catch { /* optional per-tab UI state */ }
}
