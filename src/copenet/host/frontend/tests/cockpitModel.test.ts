import assert from 'node:assert/strict';
import test from 'node:test';

import { buildAttentionRows, buildChangeRows, buildTapeRows, marketClock } from '../src/components/home/cockpitModel';
import type { MissionControlItem } from '../src/lib/missionControl';
import type { BriefMover, Portfolio, WatchlistItem } from '../src/sections/market/types';

function watch(symbol: string, change: string): WatchlistItem {
  return { symbol, name: symbol, value: '$10.00', change, tone: 'flat', spark: [] };
}

function mover(symbol: string, changePct: number): BriefMover {
  return { symbol, name: symbol, last: '$10.00', changePct, tone: changePct >= 0 ? 'up' : 'down' };
}

function portfolioHolding(symbol: string): Portfolio {
  return {
    total: '$0',
    pnl: '$0',
    pnlTone: 'flat',
    positions: [{ symbol, shares: 1, avgCost: 1, last: '$10.00', pnlPct: '+0.0%', tone: 'flat' }],
  };
}

function missionItem(overrides: Partial<MissionControlItem>): MissionControlItem {
  return {
    id: 'item',
    lane: 'needs_attention',
    kind: 'active_run',
    title: 'Title',
    detail: 'Detail',
    source: 'Agents',
    meta: '2h ago',
    sessionKey: 'session',
    runId: null,
    provider: 'openai-codex',
    model: 'gpt-5.5',
    at: new Date().toISOString(),
    ...overrides,
  };
}

test('the tape pins held names above bigger movers the operator does not own', () => {
  const rows = buildTapeRows([watch('AAPL', '+0.20%'), watch('CRWV', '+8.40%')], [], portfolioHolding('AAPL'));

  assert.deepEqual(rows.map((row) => row.symbol), ['AAPL', 'CRWV']);
  assert.equal(rows[0].held, true);
  assert.equal(rows[1].held, false);
});

test('the tape ranks unheld names by move size regardless of sign', () => {
  const rows = buildTapeRows([watch('A', '+1.00%'), watch('B', '-6.20%'), watch('C', '+3.10%')], [], null);

  assert.deepEqual(rows.map((row) => row.symbol), ['B', 'C', 'A']);
});

test('brief movers fill in symbols the watchlist has no quote for', () => {
  const rows = buildTapeRows([watch('AAPL', '+0.20%')], [mover('MU', 6.1)], null);

  assert.deepEqual(rows.map((row) => row.symbol), ['MU', 'AAPL']);
  assert.equal(rows[0].change, '+6.10%');
});

test('a symbol on both the watchlist and the movers list appears once', () => {
  const rows = buildTapeRows([watch('MU', '+6.10%')], [mover('MU', 6.1)], null);

  assert.equal(rows.length, 1);
});

test('attention keeps only what is actionable, blocking work first', () => {
  const rows = buildAttentionRows([
    missionItem({ id: 'resume', lane: 'ready_to_continue', kind: 'resume_session' }),
    missionItem({ id: 'useful', lane: 'recently_useful', kind: 'useful_run' }),
    missionItem({ id: 'failed', lane: 'needs_attention', kind: 'failed_run' }),
    missionItem({ id: 'promote', lane: 'promote_to_workflow', kind: 'workflow_candidate' }),
  ]);

  assert.deepEqual(rows.map((row) => row.id), ['failed', 'resume']);
  assert.equal(rows[0].severity, 'blocking');
  assert.equal(rows[1].severity, 'idle');
});

test('a failed run opens the run inspector, everything else opens the session', () => {
  const rows = buildAttentionRows([
    missionItem({ id: 'failed', kind: 'failed_run' }),
    missionItem({ id: 'approval', kind: 'approval' }),
  ]);

  assert.equal(rows.find((row) => row.id === 'failed')?.destination, 'observability');
  assert.equal(rows.find((row) => row.id === 'approval')?.destination, 'agents');
});

test('changes carry the market section that explains them', () => {
  const rows = buildChangeRows(
    [{ type: 'Insider', symbol: 'MSFT', headline: 'Officer bought', source: 'SEC', tone: 'up' }],
    [{ symbol: 'NVDA', kind: 'trend', detail: 'Reclaimed the 40W', tone: 'up' }],
  );

  assert.deepEqual(rows.map((row) => row.view), ['evidence', 'signals']);
  assert.equal(rows[0].symbol, 'MSFT');
});

test('the market clock reads the exchange session, not the local one', () => {
  // 2026-09-09 is a Wednesday. 14:00 UTC is 10:00 in New York — the cash session.
  assert.equal(marketClock(new Date('2026-09-09T14:00:00Z')).phase, 'open');
  assert.equal(marketClock(new Date('2026-09-09T12:00:00Z')).phase, 'pre');
  assert.equal(marketClock(new Date('2026-09-09T21:00:00Z')).phase, 'after');
  // Saturday is closed at every hour.
  assert.equal(marketClock(new Date('2026-09-12T14:00:00Z')).phase, 'closed');
});
