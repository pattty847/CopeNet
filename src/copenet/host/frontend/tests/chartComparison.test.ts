import assert from 'node:assert/strict';
import test from 'node:test';
import { buildComparisonLines, comparisonStateFromSearch, normalizeComparisonExpression } from '../src/sections/market/chartComparison';

const bars = (values: number[]) => values.map((value, index) => ({ t: 100 + index, o: value, h: value, l: value, c: value, v: 1 }));

test('comparison expressions accept ticker formulas', () => {
  assert.equal(normalizeComparisonExpression(' xlk / gld '), 'XLK / GLD');
  assert.equal(normalizeComparisonExpression('BRK.A'), 'BRK.A');
  assert.equal(normalizeComparisonExpression('(xlk + qqq) / 2'), '(XLK + QQQ) / 2');
  assert.equal(normalizeComparisonExpression('XLK;DROP'), null);
});

test('comparison URL state is reloadable and deduplicated', () => {
  assert.deepEqual(comparisonStateFromSearch('?view=compare&compare=xlk%2Fgld,GLD,GLD'), {
    expressions: ['XLK/GLD', 'GLD'],
    active: true,
  });
});

test('symbols and ratios are indexed to zero at the visible-range origin', () => {
  const lines = buildComparisonLines('AAPL', bars([100, 110, 121]), ['XLK/GLD'], [{
    expression: 'XLK / GLD',
    components: ['XLK', 'GLD'],
    points: [{ t: 100, value: 2 }, { t: 101, value: 2.2 }, { t: 102, value: 2.2 }],
    warnings: [],
  }]);
  assert.deepEqual(lines.map((line) => line.label), ['AAPL', 'XLK / GLD']);
  assert.deepEqual(lines[0].data.map((point) => Math.round(point.value)), [0, 10, 21]);
  assert.deepEqual(lines[1].data.map((point) => Math.round(point.value)), [0, 10, 10]);
});
