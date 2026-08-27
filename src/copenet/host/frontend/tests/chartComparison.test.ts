import assert from 'node:assert/strict';
import test from 'node:test';
import { buildComparisonLines, comparisonStateFromSearch, comparisonSymbols, normalizeComparisonExpression } from '../src/sections/market/chartComparison';

const bars = (values: number[]) => values.map((value, index) => ({ t: 100 + index, o: value, h: value, l: value, c: value, v: 1 }));

test('comparison expressions accept tickers and one ratio', () => {
  assert.equal(normalizeComparisonExpression(' xlk / gld '), 'XLK/GLD');
  assert.equal(normalizeComparisonExpression('BRK.A'), 'BRK.A');
  assert.equal(normalizeComparisonExpression('XLK/GLD/VOO'), null);
  assert.equal(normalizeComparisonExpression('XLK/XLK'), null);
  assert.deepEqual(comparisonSymbols(['XLK/GLD', 'GLD', '^VIX']), ['XLK', 'GLD', '^VIX']);
});

test('comparison URL state is reloadable and deduplicated', () => {
  assert.deepEqual(comparisonStateFromSearch('?view=compare&compare=xlk%2Fgld,GLD,GLD'), {
    expressions: ['XLK/GLD', 'GLD'],
    active: true,
  });
});

test('symbols and ratios are indexed to zero at the visible-range origin', () => {
  const lines = buildComparisonLines('AAPL', bars([100, 110, 121]), ['XLK/GLD'], [
    { symbol: 'XLK', bars: bars([200, 220, 242]) },
    { symbol: 'GLD', bars: bars([100, 100, 110]) },
  ]);
  assert.deepEqual(lines.map((line) => line.label), ['AAPL', 'XLK/GLD']);
  assert.deepEqual(lines[0].data.map((point) => Math.round(point.value)), [0, 10, 21]);
  assert.deepEqual(lines[1].data.map((point) => Math.round(point.value)), [0, 10, 10]);
});
