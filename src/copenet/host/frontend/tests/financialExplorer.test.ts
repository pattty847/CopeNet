import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildFinancialChartRows,
  FINANCIAL_STORIES,
  formatFinancialStoryValue,
  periodChange,
} from '../src/sections/market/financialExplorer';
import type { FinancialSeriesPayload, ValuationSeriesPayload } from '../src/sections/market/types';

const income = FINANCIAL_STORIES.find((story) => story.id === 'income')!;

function financialPayload(metric: string, observations: Array<{ periodEnd: string; value: number; fiscalYear: number }>): FinancialSeriesPayload {
  return {
    symbol: 'TEST', metric, label: metric, frequency: 'annual', basis: 'canonical', alignment: 'availability', normalizationVersion: 1, rawFactCount: observations.length, warnings: [], kind: 'financial',
    observations: observations.map((observation) => ({
      periodStart: `${observation.fiscalYear}-01-01`, periodEnd: observation.periodEnd, availableAt: `${observation.fiscalYear + 1}-02-01`, alignedAt: `${observation.fiscalYear + 1}-02-01`, value: observation.value, unit: 'USD', frequency: 'annual', fiscalYear: observation.fiscalYear, fiscalPeriod: 'FY', reported: true, derived: false, confidence: 1, qualityFlags: [], sources: [],
    })),
  };
}

test('financial explorer aligns metrics by reporting period and computes annual change', () => {
  const rows = buildFinancialChartRows([
    { metric: income.metrics[0], payload: financialPayload('revenue', [{ periodEnd: '2024-12-31', value: 100, fiscalYear: 2024 }, { periodEnd: '2025-12-31', value: 125, fiscalYear: 2025 }]) },
    { metric: income.metrics[1], payload: financialPayload('gross_profit', [{ periodEnd: '2024-12-31', value: 55, fiscalYear: 2024 }, { periodEnd: '2025-12-31', value: 70, fiscalYear: 2025 }]) },
  ]);

  assert.deepEqual(rows.map((row) => row.label), ['2024', '2025']);
  assert.equal(rows[1].revenue, 125);
  assert.equal(rows[1].gross_profit, 70);
  assert.equal(periodChange(rows, 1, 'revenue', 'annual'), 25);
});

test('period change matches the same metric fiscal period when another series inserts a row', () => {
  const quarterly = (metric: string, observations: Array<{ periodEnd: string; value: number; fiscalYear: number; fiscalPeriod: string }>): FinancialSeriesPayload => ({
    ...financialPayload(metric, []),
    frequency: 'quarterly',
    observations: observations.map((observation) => ({
      periodStart: observation.periodEnd,
      periodEnd: observation.periodEnd,
      availableAt: observation.periodEnd,
      alignedAt: observation.periodEnd,
      value: observation.value,
      unit: 'USD',
      frequency: 'quarterly',
      fiscalYear: observation.fiscalYear,
      fiscalPeriod: observation.fiscalPeriod,
      reported: true,
      derived: false,
      confidence: 1,
      qualityFlags: [],
      sources: [],
    })),
  });
  const rows = buildFinancialChartRows([
    { metric: income.metrics[0], payload: quarterly('revenue', [
      { periodEnd: '2024-03-31', value: 100, fiscalYear: 2024, fiscalPeriod: 'Q1' },
      { periodEnd: '2025-03-31', value: 125, fiscalYear: 2025, fiscalPeriod: 'Q1' },
    ]) },
    { metric: income.metrics[1], payload: quarterly('gross_profit', [
      { periodEnd: '2024-06-30', value: 60, fiscalYear: 2024, fiscalPeriod: 'Q2' },
    ]) },
  ]);

  assert.deepEqual(rows.map((row) => row.key), ['2024-03-31', '2024-06-30', '2025-03-31']);
  assert.equal(periodChange(rows, 2, 'revenue', 'quarterly'), 25);
});

test('valuation history keeps the latest observation in each calendar quarter', () => {
  const valuation = FINANCIAL_STORIES.find((story) => story.id === 'valuation')!;
  const payload: ValuationSeriesPayload = {
    symbol: 'TEST', metric: 'trailing_pe', label: 'Trailing P/E', frequency: 'price', alignment: 'price_timestamp', priceBasis: 'split_adjusted', normalizationVersion: 1, rawFactCount: 3, warnings: [], kind: 'valuation',
    observations: [
      { timestamp: '2025-01-03', alignedAt: '2025-01-03', value: 20, unit: 'ratio', price: 100, priceBasis: 'split_adjusted', qualityFlags: [], sources: [] },
      { timestamp: '2025-03-28', alignedAt: '2025-03-28', value: 24, unit: 'ratio', price: 110, priceBasis: 'split_adjusted', qualityFlags: [], sources: [] },
      { timestamp: '2025-06-27', alignedAt: '2025-06-27', value: 26, unit: 'ratio', price: 120, priceBasis: 'split_adjusted', qualityFlags: [], sources: [] },
    ],
  };
  const rows = buildFinancialChartRows([{ metric: valuation.metrics[0], payload }]);

  assert.deepEqual(rows.map((row) => row.label), ['Q1 ’25', 'Q2 ’25']);
  assert.equal(rows[0].trailing_pe, 24);
});

test('financial story formatter distinguishes percent, multiple, and money', () => {
  assert.equal(formatFinancialStoryValue(0.312, 'percent'), '31.2%');
  assert.equal(formatFinancialStoryValue(24.4, 'multiple'), '24.4×');
  assert.match(formatFinancialStoryValue(1_250_000_000, 'money', true), /^\$1\.3B$/);
});
