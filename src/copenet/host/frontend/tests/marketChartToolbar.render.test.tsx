import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { MarketChartToolbar } from '../src/sections/market/MarketChartToolbar';

test('chart toolbar keeps tools in one accessible scroll rail', () => {
  const html = renderToStaticMarkup(
    <MarketChartToolbar
      alertControl={<button type="button">Alert</button>}
      financialControls={<button type="button">Revenue</button>}
      timeframe="W"
      onTimeframe={() => undefined}
      range="5Y"
      onRange={() => undefined}
    />,
  );

  assert.match(html, /role="toolbar"/);
  assert.match(html, /aria-label="Chart tools"/);
  assert.match(html, /market-chart-toolbar__rail/);
  assert.match(html, /aria-label="Show previous chart tools"/);
  assert.match(html, /aria-label="Show more chart tools"/);
  assert.match(html, /aria-pressed="true"[^>]*>W</);
  assert.match(html, /aria-pressed="true"[^>]*>5Y</);
});
