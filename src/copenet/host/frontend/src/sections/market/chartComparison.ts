import type { Ohlcv } from './types';

const SYMBOL_PATTERN = /^[A-Z0-9.^=_-]{1,20}$/;
const COLORS = ['#fb9423', '#8fb8e8', '#69c589', '#d9ad67', '#c594e8', '#e37d9f'];

export interface ChartComparisonLine {
  id: string;
  label: string;
  color: string;
  data: { t: number; value: number }[];
}

export function normalizeComparisonExpression(raw: string): string | null {
  const compact = raw.toUpperCase().replace(/\s+/g, '');
  const parts = compact.split('/');
  if (parts.length > 2 || parts.some((part) => !SYMBOL_PATTERN.test(part))) return null;
  if (parts.length === 2 && parts[0] === parts[1]) return null;
  return parts.join('/');
}

export function comparisonSymbols(expressions: string[]): string[] {
  return [...new Set(expressions.flatMap((expression) => expression.split('/')))];
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

function expressionPoints(expression: string, series: Map<string, Ohlcv[]>): { t: number; value: number }[] {
  const [numerator, denominator] = expression.split('/');
  const numeratorBars = series.get(numerator) ?? [];
  if (!denominator) return numeratorBars.map((bar) => ({ t: bar.t, value: bar.c }));
  const denominatorByTime = new Map((series.get(denominator) ?? []).map((bar) => [bar.t, bar.c]));
  return numeratorBars.flatMap((bar) => {
    const divisor = denominatorByTime.get(bar.t);
    return divisor && Number.isFinite(divisor) ? [{ t: bar.t, value: bar.c / divisor }] : [];
  });
}

export function buildComparisonLines(
  baseSymbol: string,
  baseBars: Ohlcv[],
  expressions: string[],
  fetched: { symbol: string; bars: Ohlcv[] }[],
): ChartComparisonLine[] {
  if (!baseBars.length) return [];
  const start = baseBars[0].t;
  const end = baseBars[baseBars.length - 1].t;
  const series = new Map(fetched.map((row) => [row.symbol, row.bars]));
  series.set(baseSymbol, baseBars);
  return [baseSymbol, ...expressions.filter((expression) => expression !== baseSymbol)].map((expression, index) => {
    const raw = expressionPoints(expression, series).filter((point) => point.t >= start && point.t <= end && Number.isFinite(point.value) && point.value > 0);
    const origin = raw[0]?.value;
    return {
      id: expression,
      label: expression,
      color: COLORS[index % COLORS.length],
      data: origin ? raw.map((point) => ({ t: point.t, value: ((point.value / origin) - 1) * 100 })) : [],
    };
  }).filter((line) => line.data.length > 1);
}
