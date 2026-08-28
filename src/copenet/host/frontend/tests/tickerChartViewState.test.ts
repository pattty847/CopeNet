import assert from 'node:assert/strict';
import test from 'node:test';

import {
  DEFAULT_TICKER_CHART_VIEW,
  readTickerChartViewState,
  writeTickerChartViewState,
} from '../src/sections/market/tickerChartViewState';

test('ticker chart investigation state round-trips through per-tab storage', () => {
  let stored: string | null = null;
  const storage = {
    getItem: () => stored,
    setItem: (_key: string, value: string) => { stored = value; },
  };
  const state = {
    timeframe: 'D' as const,
    range: '1Y' as const,
    overlayMetric: 'revenue',
    overlayFrequency: 'annual' as const,
    showInsiderTransactions: true,
    insiderLookback: '90D' as const,
    insiderDisplayMode: 'individual' as const,
  };

  writeTickerChartViewState(state, storage);

  assert.deepEqual(readTickerChartViewState(storage), state);
});

test('ticker chart investigation state rejects malformed stored values', () => {
  const storage = {
    getItem: () => JSON.stringify({
      timeframe: 'hourly',
      range: 'forever',
      overlayMetric: 42,
      overlayFrequency: 'weekly',
      showInsiderTransactions: 'yes',
      insiderLookback: 'century',
      insiderDisplayMode: 'heatmap',
    }),
  };

  assert.deepEqual(readTickerChartViewState(storage), DEFAULT_TICKER_CHART_VIEW);
});
