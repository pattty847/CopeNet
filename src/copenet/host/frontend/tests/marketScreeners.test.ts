import assert from 'node:assert/strict';
import test from 'node:test';
import { sortCandidates } from '../src/sections/market/screeners/model';
import type { Candidate, Preset, ScreenerRun } from '../src/sections/market/screeners/types';
import { marketSectionFromLocation, marketSectionPath } from '../src/lib/appSectionRouting';
import { formatRuleValue, outsideWindow, ruleColumns, ruleWindows, windowPosition } from '../src/sections/market/screeners/ruleWindows';
import { metricHistogram, summarizeScreen } from '../src/sections/market/screeners/screenSummary';
import { previousRunId, screenChurn } from '../src/sections/market/screeners/churn';
import { STRIP_HEIGHT, setupVisualModel } from '../src/sections/market/screeners/setupVisualModel';

const preset = (id: string, direction = 'Either', metric = 'bandWidth', ascending = true): Preset => ({
  id,
  name: id,
  direction,
  metric,
  ascending,
  description: '',
  rules: [],
  next: '',
});
const candidate = (symbol: string, fields: Partial<Candidate> = {}): Candidate => ({
  id: `NYSE:${symbol}`,
  symbol,
  exchange: 'NYSE',
  name: symbol,
  sector: 'Finance',
  direction: 'Either',
  price: 100,
  change: 1,
  marketCap: 20e9,
  dollarVolume: 50e6,
  averageVolume: 5e5,
  relativeVolume: 1,
  rsi: 50,
  sma50: 98,
  sma200: 90,
  high52: 105,
  monthReturn: 2,
  bandWidth: 5,
  distance50: 2,
  distance200: 11,
  drawdown: -4.8,
  updateMode: 'delayed',
  ...fields,
});
const run = (id: string, finishedAt: string, symbols: string[]): ScreenerRun => ({
  id,
  version: 1,
  startedAt: finishedAt,
  finishedAt,
  status: 'complete',
  error: null,
  config: { minCap: 10e9, maxCap: null, minPrice: 10, minDollarVolume: 25e6 },
  presets: [preset('compression')],
  source: 'test',
  received: 10,
  truncated: false,
  eligible: 8,
  excluded: {},
  screens: [{ id: 'compression', rows: symbols.map((symbol) => candidate(symbol)), missingFields: 0 }],
});

test('screeners have a first-class Market route', () => {
  assert.equal(marketSectionFromLocation('/market', '?view=screeners'), 'screeners');
  assert.equal(marketSectionPath('screeners'), '/market?view=screeners');
});

test('candidate sorting keeps unknown metrics last and leaves snapshot order unchanged', () => {
  const rows = [{ id: 'B', rsi: 35 }, { id: 'A', rsi: null }, { id: 'C', rsi: 60 }] as Candidate[];
  assert.deepEqual(sortCandidates(rows, 'rsi', false).map((row) => row.id), ['C', 'B', 'A']);
  assert.deepEqual(sortCandidates(rows, 'rsi', true).map((row) => row.id), ['B', 'C', 'A']);
  assert.deepEqual(rows.map((row) => row.id), ['B', 'A', 'C']);
});

test('rule windows place a value inside its bounds and flag values past the edge', () => {
  const [bandWidth, drawdown, rsi] = ruleWindows(preset('compression'));
  assert.equal(windowPosition(bandWidth, 2.5), 0.25);
  assert.equal(windowPosition(drawdown, -10), 0);
  assert.equal(windowPosition(rsi, 65), 1);
  assert.equal(windowPosition(rsi, null), null);
  assert.equal(windowPosition(rsi, 70), 1);
  assert.ok(outsideWindow(rsi, 70));
  assert.ok(!outsideWindow(rsi, 65));
  assert.equal(formatRuleValue(bandWidth, 2.5), '2.5%');
  assert.equal(formatRuleValue(drawdown, -3.25), '-3.3%');
  assert.equal(formatRuleValue(ruleWindows(preset('pullback'))[0], 1.2), '+1.2%');
  assert.equal(formatRuleValue(ruleWindows(preset('expansion'))[0], 2.345), '2.35×');
  assert.equal(formatRuleValue(rsi, null), '—');
});

test('table rule columns omit unbounded and context-duplicated rules', () => {
  assert.deepEqual(ruleColumns(preset('oversold')).map((rule) => rule.key), ['rsi', 'drawdown']);
  assert.deepEqual(ruleColumns(preset('expansion')).map((rule) => rule.key), ['relativeVolume']);
  assert.deepEqual(ruleColumns(preset('unknown')), []);
});

test('screen summary reports hit rate, sector concentration and medians', () => {
  const rows = [
    candidate('A', { sector: 'Finance', change: 1, dollarVolume: 10 }),
    candidate('B', { sector: 'Finance', change: -1, dollarVolume: 30 }),
    candidate('C', { sector: 'Utilities', change: 3, dollarVolume: 20 }),
    candidate('D', { sector: null, change: null, dollarVolume: 40 }),
  ];
  const summary = summarizeScreen(rows, 16, 2);
  assert.equal(summary.count, 4);
  assert.equal(summary.hitRate, 0.25);
  assert.deepEqual(summary.sectors, [
    { name: 'Finance', count: 2 },
    { name: 'Sector unavailable', count: 1 },
  ]);
  assert.equal(summary.otherSectors, 1);
  assert.equal(summary.medians.change, 1);
  assert.equal(summary.medians.dollarVolume, 25);
  assert.equal(summarizeScreen([], 0).hitRate, 0);
});

test('metric histogram bins values across the rule window and clamps the edges', () => {
  const rule = ruleWindows(preset('compression'))[0];
  const rows = [candidate('A', { bandWidth: 0 }), candidate('B', { bandWidth: 9.99 }), candidate('C', { bandWidth: 10 }), candidate('D', { bandWidth: null })];
  const bins = metricHistogram(rows, rule, 10);
  assert.equal(bins[0], 1);
  assert.equal(bins[9], 2);
  assert.equal(bins.reduce((sum, value) => sum + value, 0), 3);
});

test('churn is the set difference against the previous complete observation', () => {
  const previous = run('a'.repeat(32), '2026-09-09T20:30:00Z', ['AAA', 'BBB', 'CCC']);
  const latest = run('b'.repeat(32), '2026-09-10T20:30:00Z', ['BBB', 'DDD']);
  const churn = screenChurn(latest, previous);
  assert.deepEqual([...churn.compression.added], ['DDD']);
  assert.equal(churn.compression.dropped, 2);
  const first = screenChurn(latest, null);
  assert.equal(first.compression.added.size, 0);
  assert.equal(first.compression.dropped, 0);
  const history = [
    { id: latest.id, startedAt: '', finishedAt: latest.finishedAt, status: 'complete' as const, error: null },
    { id: 'c'.repeat(32), startedAt: '', finishedAt: '2026-09-09T22:00:00Z', status: 'error' as const, error: 'x' },
    { id: previous.id, startedAt: '', finishedAt: previous.finishedAt, status: 'complete' as const, error: null },
  ];
  assert.equal(previousRunId(history, latest), previous.id);
  assert.equal(previousRunId(history, previous), null);
});

test('setup visual draws the rule zone at the observation and fits the RSI strip to its window', () => {
  const bars = Array.from({ length: 300 }, (_, index) => {
    const close = 100 + Math.sin(index / 9) * 6 + index * 0.05;
    return { t: 1_700_000_000 + index * 86_400, o: close, h: close + 1, l: close - 1, c: close, v: 1_000_000 + (index % 7) * 50_000 };
  });
  const model = setupVisualModel(bars, preset('compression'), candidate('AAA'), 336)!;
  assert.ok(model.zone && model.zone.tone === 'either');
  assert.ok(model.bandPath && model.bandPath.endsWith('Z'));
  assert.ok(model.zone!.top < model.zone!.bottom);
  assert.ok(model.observedX > 200 && model.observedX < 336 - 84 + 1);
  assert.ok(model.pricePath.startsWith('M8.0 '));
  assert.equal(model.strip.kind, 'rsi');
  if (model.strip.kind === 'rsi') {
    assert.ok(model.strip.windowTop! > 0 && model.strip.windowBottom! < STRIP_HEIGHT);
    assert.ok(model.strip.windowBottom! - model.strip.windowTop! > 12, 'window is drawn as a band, not a sliver');
  }
  const pullback = setupVisualModel(bars, preset('pullback', 'Bullish', 'distance50'), candidate('AAA'), 336)!;
  assert.equal(pullback.zone?.tone, 'up');
  assert.ok(pullback.overlays.some((overlay) => overlay.key === 'sma200'));
  const expansion = setupVisualModel(bars, preset('expansion', 'Either', 'relativeVolume', false), candidate('AAA', { relativeVolume: 2.3 }), 336)!;
  assert.equal(expansion.zone, null);
  assert.equal(expansion.strip.kind, 'volume');
  if (expansion.strip.kind === 'volume') assert.equal(expansion.strip.bars.filter((bar) => bar.last).length, 1);
  assert.equal(setupVisualModel(bars.slice(0, 1), preset('compression'), candidate('AAA'), 336), null);
});
