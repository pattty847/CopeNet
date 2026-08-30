import assert from 'node:assert/strict';
import test from 'node:test';
import { assetProfile } from '../src/sections/market/assetProfile';
import { CHART_RANGES, timeframeLabel, visibleBars } from '../src/sections/market/chartRanges';
import { buildRailEntries, stepRail } from '../src/sections/market/symbolRailModel';
import { nextSnap, pushRecent } from '../src/sections/market/tickerWorkspaceState';
import { fractionAsPercent, signedPct } from '../src/sections/market/workspaceViz';
import type { TickerDetailPayload, WatchlistItem } from '../src/sections/market/types';

const DAY = 86400;
const bars = (count: number) => Array.from({ length: count }, (_, index) => ({ t: index * DAY, o: 1, h: 1, l: 1, c: 1, v: 1 }));

const watchItem = (symbol: string): WatchlistItem => ({ symbol, name: symbol, value: '1', change: '+1%', tone: 'up', spark: [1, 2] });

test('visible range trims from the newest bar, and MAX keeps everything', () => {
  const series = bars(400);
  assert.equal(visibleBars(series, 'MAX').length, 400);
  // 6M is 183 days of a daily series, inclusive of the cutoff bar.
  assert.equal(visibleBars(series, '6M').length, 184);
  assert.equal(visibleBars([], '1Y').length, 0);
  assert.deepEqual(CHART_RANGES, ['6M', '1Y', '3Y', '5Y', 'MAX']);
  assert.equal(timeframeLabel('W'), 'Weekly');
});

test('the rail is an ordered traversal with no duplicates, and always contains the current symbol', () => {
  const entries = buildRailEntries({
    watchlist: [watchItem('XLK'), watchItem('SMH')],
    recents: ['NVDA', 'XLK'],
    peers: ['VOO', 'SMH'],
    current: 'GOOG',
  });
  assert.deepEqual(entries.map((entry) => entry.symbol), ['XLK', 'SMH', 'GOOG', 'NVDA', 'VOO']);
  // A symbol keeps the group it was first seen in; the current symbol is never missing.
  assert.equal(entries.find((entry) => entry.symbol === 'GOOG')?.group, 'Recent');
  assert.equal(entries.find((entry) => entry.symbol === 'XLK')?.group, 'Watchlist');
});

test('j/k steps the rail and stops at the ends rather than wrapping', () => {
  const entries = buildRailEntries({ watchlist: [watchItem('A'), watchItem('B')], recents: [], peers: [], current: 'C' });
  assert.equal(stepRail(entries, 'A', 1), 'B');
  assert.equal(stepRail(entries, 'B', -1), 'A');
  // Wrapping past the end would silently jump the operator to the far end of the list.
  assert.equal(stepRail(entries, 'C', 1), null);
  assert.equal(stepRail(entries, 'A', -1), null);
  // An unknown symbol lands on the first entry instead of nowhere.
  assert.equal(stepRail(entries, 'ZZZZ', 1), 'A');
  assert.equal(stepRail([], 'A', 1), null);
});

test('a fund is routed away from issuer tabs it can never fill', () => {
  const base = { symbol: 'X', name: 'X' } as unknown as TickerDetailPayload;
  const fund = { ...base, intelligence: { exposure: { source: 'yf', topHoldings: [{ symbol: 'NVDA' }] } } } as unknown as TickerDetailPayload;
  const issuer = { ...base, intelligence: { exposure: null } } as unknown as TickerDetailPayload;

  assert.equal(assetProfile(fund).kind, 'fund');
  assert.equal(assetProfile(fund).tabs.includes('fundamentals'), false);
  assert.equal(assetProfile(fund).tabs.includes('evidence'), false);
  // Overview survives, because that is where the fund's holdings and sector weights live.
  assert.equal(assetProfile(fund).tabs.includes('overview'), true);

  assert.equal(assetProfile(issuer).kind, 'issuer');
  assert.equal(assetProfile(issuer).tabs.includes('fundamentals'), true);
  // An unresolved asset is treated as an issuer rather than being stripped of tabs.
  assert.equal(assetProfile(null).kind, 'issuer');
});

test('drawer snap cycles through all three heights', () => {
  assert.equal(nextSnap('collapsed'), 'half');
  assert.equal(nextSnap('half'), 'full');
  assert.equal(nextSnap('full'), 'collapsed');
});

test('recents are newest-first, de-duplicated, and bounded', () => {
  assert.deepEqual(pushRecent('B', ['A', 'B', 'C']), ['B', 'A', 'C']);
  assert.deepEqual(pushRecent('D', ['A', 'B'], 2), ['D', 'A']);
});

test('fundamentals growth is a fraction and must be scaled before display', () => {
  // The backend field is named `yoy_pct` but holds (value - prior) / |prior|. Rendering it
  // straight through showed a +20% quarter as "+0.2%".
  assert.equal(fractionAsPercent(0.2), 20);
  assert.equal(fractionAsPercent(-0.135), -13.5);
  assert.equal(fractionAsPercent(null), null);
  assert.equal(fractionAsPercent(Number.NaN), null);
  assert.equal(signedPct(fractionAsPercent(0.2)), '+20.0%');
});
