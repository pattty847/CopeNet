import type {
  FinancialFrequency,
  FinancialSeriesObservation,
  FinancialSeriesPayload,
  FinancialSeriesSource,
  OverlaySeriesPayload,
  ValuationSeriesObservation,
  ValuationSeriesPayload,
} from './types';

export type FinancialStoryId = 'income' | 'cash-flow' | 'margins' | 'balance-sheet' | 'per-share' | 'valuation';
export type FinancialValueKind = 'money' | 'percent' | 'multiple' | 'per-share';

export interface FinancialStoryMetric {
  id: string;
  label: string;
  shortLabel: string;
  color: string;
}

export interface FinancialStory {
  id: FinancialStoryId;
  label: string;
  description: string;
  chart: 'bar' | 'line';
  valueKind: FinancialValueKind;
  defaultFrequency: FinancialFrequency;
  frequencies: FinancialFrequency[];
  metrics: FinancialStoryMetric[];
}

const BLUE = '#4b8ff7';
const CYAN = '#4cc9d7';
const ORANGE = '#fb9423';
const VIOLET = '#a886f7';

export const FINANCIAL_STORIES: FinancialStory[] = [
  {
    id: 'income',
    label: 'Income',
    description: 'Scale and profit progression from the same reporting periods.',
    chart: 'bar',
    valueKind: 'money',
    defaultFrequency: 'annual',
    frequencies: ['annual', 'quarterly'],
    metrics: [
      { id: 'revenue', label: 'Revenue', shortLabel: 'Revenue', color: BLUE },
      { id: 'gross_profit', label: 'Gross profit', shortLabel: 'Gross profit', color: CYAN },
      { id: 'operating_income', label: 'Operating income', shortLabel: 'Operating', color: ORANGE },
      { id: 'net_income', label: 'Net income', shortLabel: 'Net income', color: VIOLET },
    ],
  },
  {
    id: 'cash-flow',
    label: 'Cash flow',
    description: 'Operating cash generation, reinvestment, and residual free cash flow.',
    chart: 'bar',
    valueKind: 'money',
    defaultFrequency: 'annual',
    frequencies: ['annual', 'quarterly', 'ttm'],
    metrics: [
      { id: 'operating_cash_flow', label: 'Operating cash flow', shortLabel: 'Operating cash', color: BLUE },
      { id: 'capex', label: 'Capital expenditures', shortLabel: 'Capex', color: ORANGE },
      { id: 'fcf', label: 'Free cash flow', shortLabel: 'Free cash flow', color: CYAN },
    ],
  },
  {
    id: 'margins',
    label: 'Margins',
    description: 'How efficiently revenue converts into gross, operating, and free cash flow.',
    chart: 'line',
    valueKind: 'percent',
    defaultFrequency: 'annual',
    frequencies: ['annual', 'quarterly', 'ttm'],
    metrics: [
      { id: 'gross_margin', label: 'Gross margin', shortLabel: 'Gross margin', color: BLUE },
      { id: 'operating_margin', label: 'Operating margin', shortLabel: 'Operating margin', color: ORANGE },
      { id: 'fcf_margin', label: 'Free cash flow margin', shortLabel: 'FCF margin', color: CYAN },
    ],
  },
  {
    id: 'balance-sheet',
    label: 'Balance sheet',
    description: 'Liquidity, net leverage, and the equity capital base.',
    chart: 'bar',
    valueKind: 'money',
    defaultFrequency: 'annual',
    frequencies: ['annual', 'quarterly'],
    metrics: [
      { id: 'cash_equivalents', label: 'Cash and equivalents', shortLabel: 'Cash', color: CYAN },
      { id: 'net_debt', label: 'Net debt', shortLabel: 'Net debt', color: ORANGE },
      { id: 'stockholders_equity', label: "Stockholders' equity", shortLabel: 'Equity', color: BLUE },
    ],
  },
  {
    id: 'per-share',
    label: 'Per share',
    description: 'Earnings and revenue measured against the diluted share base.',
    chart: 'line',
    valueKind: 'per-share',
    defaultFrequency: 'annual',
    frequencies: ['annual', 'quarterly'],
    metrics: [
      { id: 'diluted_eps', label: 'Diluted earnings per share', shortLabel: 'Diluted EPS', color: BLUE },
      { id: 'revenue_per_share', label: 'Revenue per diluted share', shortLabel: 'Revenue / share', color: CYAN },
    ],
  },
  {
    id: 'valuation',
    label: 'Valuation',
    description: 'Then-known trailing fundamentals against split-adjusted traded prices.',
    chart: 'line',
    valueKind: 'multiple',
    defaultFrequency: 'ttm',
    frequencies: ['ttm'],
    metrics: [
      { id: 'trailing_pe', label: 'Trailing price / earnings', shortLabel: 'P/E', color: BLUE },
      { id: 'trailing_ps', label: 'Trailing price / sales', shortLabel: 'P/S', color: CYAN },
      { id: 'trailing_pfcf', label: 'Trailing price / free cash flow', shortLabel: 'P/FCF', color: ORANGE },
    ],
  },
];

export interface FinancialCellMeta {
  availableAt: string | null;
  periodEnd: string | null;
  fiscalYear: number | null;
  fiscalPeriod: string | null;
  source: FinancialSeriesSource | null;
  reported: boolean;
  derived: boolean;
}

export interface FinancialChartRow {
  key: string;
  label: string;
  timestamp: number;
  _meta: Record<string, FinancialCellMeta>;
  [metric: string]: string | number | Record<string, FinancialCellMeta>;
}

export interface FinancialMetricPayload {
  metric: FinancialStoryMetric;
  payload: OverlaySeriesPayload | null;
}

function quarterLabel(date: Date): string {
  return `Q${Math.floor(date.getUTCMonth() / 3) + 1} ’${String(date.getUTCFullYear()).slice(-2)}`;
}

function financialObservationLabel(observation: FinancialSeriesObservation, frequency: FinancialFrequency): string {
  const date = new Date(`${observation.periodEnd}T00:00:00Z`);
  if (frequency === 'annual') return String(observation.fiscalYear ?? date.getUTCFullYear());
  const fiscalPeriod = observation.fiscalPeriod && !['FY', 'TTM'].includes(observation.fiscalPeriod) ? observation.fiscalPeriod : null;
  return `${fiscalPeriod ?? `Q${Math.floor(date.getUTCMonth() / 3) + 1}`} ’${String(observation.fiscalYear ?? date.getUTCFullYear()).slice(-2)}`;
}

function valuationRows(payload: ValuationSeriesPayload): Array<{ key: string; label: string; timestamp: number; value: number; meta: FinancialCellMeta }> {
  const quarterly = new Map<string, ValuationSeriesObservation>();
  payload.observations.forEach((observation) => {
    if (observation.value == null || !Number.isFinite(observation.value)) return;
    const date = new Date(`${observation.timestamp}T00:00:00Z`);
    const key = `${date.getUTCFullYear()}-Q${Math.floor(date.getUTCMonth() / 3) + 1}`;
    quarterly.set(key, observation);
  });
  return [...quarterly.entries()].map(([key, observation]) => {
    const date = new Date(`${observation.timestamp}T00:00:00Z`);
    return {
      key,
      label: quarterLabel(date),
      timestamp: date.getTime(),
      value: observation.value as number,
      meta: {
        availableAt: observation.epsAvailableAt ?? observation.denominatorAvailableAt ?? observation.sharesAvailableAt ?? null,
        periodEnd: observation.epsPeriodEnd ?? observation.denominatorPeriodEnd ?? observation.timestamp,
        fiscalYear: date.getUTCFullYear(),
        fiscalPeriod: `Q${Math.floor(date.getUTCMonth() / 3) + 1}`,
        source: observation.sources[0] ?? null,
        reported: false,
        derived: true,
      },
    };
  });
}

function financialRows(payload: FinancialSeriesPayload): Array<{ key: string; label: string; timestamp: number; value: number; meta: FinancialCellMeta }> {
  return payload.observations.flatMap((observation) => {
    if (!Number.isFinite(observation.value)) return [];
    const timestamp = Date.parse(`${observation.periodEnd}T00:00:00Z`);
    return [{
      key: observation.periodEnd,
      label: financialObservationLabel(observation, payload.frequency),
      timestamp,
      value: observation.value,
      meta: {
        availableAt: observation.availableAt,
        periodEnd: observation.periodEnd,
        fiscalYear: observation.fiscalYear,
        fiscalPeriod: observation.fiscalPeriod,
        source: observation.sources[0] ?? null,
        reported: observation.reported,
        derived: observation.derived,
      },
    }];
  });
}

export function buildFinancialChartRows(series: FinancialMetricPayload[], limit = 12): FinancialChartRow[] {
  const combined = new Map<string, FinancialChartRow>();
  series.forEach(({ metric, payload }) => {
    if (!payload) return;
    const observations = payload.kind === 'valuation' ? valuationRows(payload) : financialRows(payload);
    observations.forEach((observation) => {
      const row = combined.get(observation.key) ?? {
        key: observation.key,
        label: observation.label,
        timestamp: observation.timestamp,
        _meta: {},
      };
      row[metric.id] = observation.value;
      row._meta[metric.id] = observation.meta;
      combined.set(observation.key, row);
    });
  });
  return [...combined.values()].sort((a, b) => a.timestamp - b.timestamp).slice(-limit);
}

export function periodChange(rows: FinancialChartRow[], rowIndex: number, metricId: string, frequency: FinancialFrequency): number | null {
  const current = rows[rowIndex]?.[metricId];
  const currentMeta = rows[rowIndex]?._meta[metricId];
  if (typeof current !== 'number' || !currentMeta) return null;
  const previousRow = rows.slice(0, rowIndex).reverse().find((row) => {
    if (typeof row[metricId] !== 'number') return false;
    const previousMeta = row._meta[metricId];
    if (!previousMeta) return false;
    if (currentMeta.fiscalYear != null && previousMeta.fiscalYear !== currentMeta.fiscalYear - 1) return false;
    if (frequency === 'annual') return true;
    if (currentMeta.fiscalPeriod && previousMeta.fiscalPeriod) return previousMeta.fiscalPeriod === currentMeta.fiscalPeriod;
    if (!currentMeta.periodEnd || !previousMeta.periodEnd) return false;
    return new Date(`${previousMeta.periodEnd}T00:00:00Z`).getUTCMonth() === new Date(`${currentMeta.periodEnd}T00:00:00Z`).getUTCMonth();
  });
  const previous = previousRow?.[metricId];
  if (typeof current !== 'number' || typeof previous !== 'number' || previous === 0) return null;
  return ((current / previous) - 1) * 100;
}

export function formatFinancialStoryValue(value: number, kind: FinancialValueKind, compact = false): string {
  if (kind === 'percent') return new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 }).format(value);
  if (kind === 'multiple') return `${new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 }).format(value)}×`;
  if (kind === 'per-share') return new Intl.NumberFormat(undefined, { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(value);
  return new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: 'USD',
    notation: compact ? 'compact' : 'standard',
    maximumFractionDigits: compact ? 1 : 0,
  }).format(value);
}
