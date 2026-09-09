import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';

import { ChartClusterBoxes } from '../src/sections/market/ChartClusterBoxes';
import type { RenderedBox } from '../src/sections/market/chartDecorations';

function box(overrides: Partial<RenderedBox> = {}): RenderedBox {
  return {
    key: 'cluster',
    left: 100,
    top: 80,
    width: 140,
    height: 60,
    avgY: 110,
    avgPrice: 18.06,
    avgSide: 'buy',
    chip: '▲1 ▼6 ●16 · net $251K',
    tone: 'up',
    items: [],
    firstTime: 1,
    rangeLabel: 'Sep 1 – Sep 8',
    ...overrides,
  };
}

test('cluster summary owns the average label while the box keeps its dashed line', () => {
  const html = renderToStaticMarkup(<ChartClusterBoxes boxes={[box()]} onOpen={() => {}} />);

  assert.match(html, /data-cluster-average-line/);
  assert.match(html, /data-cluster-average-label/);
  assert.match(html, /avg buy \$18\.06/);
  assert.equal((html.match(/avg buy \$18\.06/g) ?? []).length, 2); // visible label + button aria-label
});

test('cluster without a priced average keeps a compact one-line summary', () => {
  const html = renderToStaticMarkup(
    <ChartClusterBoxes boxes={[box({ avgY: null, avgPrice: null })]} onOpen={() => {}} />,
  );

  assert.doesNotMatch(html, /data-cluster-average-line/);
  assert.doesNotMatch(html, /data-cluster-average-label/);
  assert.doesNotMatch(html, /avg buy/);
});
