import type { FormulaSeries, Ohlcv } from './types';

const EXPRESSION_PATTERN = /^[A-Z0-9.^=_+\-*/()\s]+$/;
const COLORS = ['#fb9423', '#8fb8e8', '#69c589', '#d9ad67', '#c594e8', '#e37d9f'];

export interface ChartComparisonLine {
  id: string;
  label: string;
  color: string;
  data: { t: number; value: number }[];
  valueMode: 'percent' | 'number';
}

export function normalizeComparisonExpression(raw: string): string | null {
  const normalized = raw.trim().toUpperCase().replace(/\s+/g, ' ');
  if (!normalized || normalized.length > 200 || !EXPRESSION_PATTERN.test(normalized)) return null;
  return normalized;
}

export function comparisonStateFromSearch(search: string): { expressions: string[]; active: boolean } {
  const params = new URLSearchParams(search);
  const expressions = (params.get('compare') ?? '')
    .split(',')
    .map(normalizeComparisonExpression)
    .filter((value): value is string => value != null)
    .slice(0, 5);
  return { expressions: [...new Set(expressions)], active: params.get('view') === 'compare' && expressions.length > 0 };
}

export function comparisonSearch(expressions: string[], active: boolean): string {
  const params = new URLSearchParams(window.location.search);
  if (expressions.length) params.set('compare', expressions.join(','));
  else params.delete('compare');
  if (active && expressions.length) params.set('view', 'compare');
  else params.delete('view');
  const next = params.toString();
  return next ? `?${next}` : '';
}

export function buildComparisonLines(
  baseSymbol: string,
  baseBars: Ohlcv[],
  expressions: string[],
  formulas: FormulaSeries[],
): ChartComparisonLine[] {
  if (!baseBars.length) return [];
  const start = baseBars[0].t;
  const end = baseBars[baseBars.length - 1].t;
  const rows = [
    { id: baseSymbol, label: baseSymbol, points: baseBars.map((bar) => ({ t: bar.t, value: bar.c })) },
    ...formulas.map((formula, index) => ({
      id: expressions[index] ?? formula.expression,
      label: formula.expression,
      points: formula.points,
    })).filter((row) => row.label !== baseSymbol),
  ];
  return rows.map((row, index) => {
    const raw = row.points.filter((point) => point.t >= start && point.t <= end && Number.isFinite(point.value));
    const originIndex = raw.findIndex((point) => point.value !== 0);
    const indexed = originIndex >= 0 ? raw.slice(originIndex) : [];
    const origin = indexed[0]?.value;
    return {
      id: row.id,
      label: row.label,
      color: COLORS[index % COLORS.length],
      valueMode: 'percent' as const,
      data: origin ? indexed.map((point) => ({ t: point.t, value: ((point.value / origin) - 1) * 100 })) : [],
    };
  }).filter((line) => line.data.length > 1);
}
