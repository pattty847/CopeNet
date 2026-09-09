import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildPulseTabs,
  formatCount,
  formatErrorRate,
  formatLatency,
  marketClock,
  pulseRows,
  relativeAge,
} from '../src/components/home/deskModel';
import { DEFAULT_LAUNCH_IDS, LAUNCH_SLOTS, resolveLaunchTiles } from '../src/components/home/quickLaunch';
import { TOOL_SHORTCUTS } from '../src/components/home/dataTools';
import type { MacroItem, WatchlistItem } from '../src/sections/market/types';

function watch(symbol: string): WatchlistItem {
  return { symbol, name: symbol, value: '$10.00', change: '+1.00%', tone: 'up', spark: [1, 2] };
}

function macro(label: string): MacroItem {
  return { label, value: '15.1', change: '-4.2%', tone: 'down', spark: [3, 2] };
}

// ----------------------------------------------------------------------- market clock

test('the market clock reads the exchange session, not the local one', () => {
  // 2026-09-09 is a Wednesday. 14:00 UTC is 10:00 in New York — the cash session.
  assert.equal(marketClock(new Date('2026-09-09T14:00:00Z')).phase, 'open');
  assert.equal(marketClock(new Date('2026-09-09T12:00:00Z')).phase, 'pre');
  assert.equal(marketClock(new Date('2026-09-09T21:00:00Z')).phase, 'after');
  assert.equal(marketClock(new Date('2026-09-12T14:00:00Z')).phase, 'closed');
});

// ----------------------------------------------------------------------- market pulse

test('pulse tabs follow the operator watchlists so a screener drop needs no code change', () => {
  const tabs = buildPulseTabs(['Default', 'Screener Sep 9', '  ']);

  assert.deepEqual(tabs.map((tab) => tab.label), ['Default', 'Screener Sep 9', 'Macro']);
  assert.deepEqual(tabs.map((tab) => tab.kind), ['watchlist', 'watchlist', 'macro']);
});

test('macro rows are not navigable — an index is not a tradeable ticker', () => {
  const tabs = buildPulseTabs(['Default']);

  const listRows = pulseRows(tabs[0], [watch('AAPL')], [macro('VIX')]);
  const macroRows = pulseRows(tabs[1], [watch('AAPL')], [macro('VIX')]);

  assert.equal(listRows[0].navigable, true);
  assert.equal(listRows[0].symbol, 'AAPL');
  assert.equal(macroRows[0].navigable, false);
  assert.equal(macroRows[0].symbol, 'VIX');
});

// ------------------------------------------------------------------------ health copy

test('latency is an em dash when nothing completed, never a suspiciously fast zero', () => {
  assert.equal(formatLatency(null), '—');
  assert.equal(formatLatency(742), '742 ms');
  assert.equal(formatLatency(2400), '2.4 s');
});

test('an error rate over no runs is unknown rather than a clean hour the desk never had', () => {
  assert.equal(formatErrorRate(0, 0), '—');
  assert.equal(formatErrorRate(0, 12), '0.0%');
  assert.equal(formatErrorRate(0.25, 12), '25%');
});

test('counts stay short once they stop being scannable', () => {
  assert.equal(formatCount(592), '592');
  assert.equal(formatCount(12_400), '12.4k');
});

test('activity ages read in desk terms', () => {
  const now = Date.parse('2026-09-09T15:00:00Z');
  assert.equal(relativeAge('2026-09-09T14:59:40Z', now), 'just now');
  assert.equal(relativeAge('2026-09-09T14:51:00Z', now), '9m ago');
  assert.equal(relativeAge('2026-09-09T12:00:00Z', now), '3h ago');
  assert.equal(relativeAge('2026-09-07T15:00:00Z', now), '2d ago');
  assert.equal(relativeAge('not a date', now), '');
});

// ------------------------------------------------------------------------ quick launch

test('an empty saved list means the defaults, not an empty launcher', () => {
  assert.deepEqual(resolveLaunchTiles([]).map((tile) => tile.id), DEFAULT_LAUNCH_IDS);
});

test('a saved tile id that no longer exists is dropped rather than rendered dead', () => {
  const tiles = resolveLaunchTiles(['market_radar', 'a_tile_that_was_removed', 'scans']);

  assert.deepEqual(tiles.map((tile) => tile.id), ['market_radar', 'scans']);
});

test('quick launch never renders more than its slots', () => {
  const everyTile = resolveLaunchTiles([
    'market_radar', 'new_session', 'signals', 'watchlists', 'scans', 'evidence', 'portfolio', 'runs',
  ]);

  assert.equal(everyTile.length, LAUNCH_SLOTS);
});

test('every data-and-tools tile points at a destination that exists', () => {
  const marketViews = new Set(['briefing', 'structure', 'signals', 'portfolio', 'evidence', 'ledger', 'backtest', 'scans', 'watchlist']);
  const sections = new Set(['home', 'agents', 'market', 'workflows', 'data-tools', 'observability', 'experiments']);

  for (const tool of TOOL_SHORTCUTS) {
    if (tool.destination.kind === 'market') assert.ok(marketViews.has(tool.destination.view), tool.id);
    else assert.ok(sections.has(tool.destination.section), tool.id);
  }
});
