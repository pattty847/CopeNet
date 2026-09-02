import assert from 'node:assert/strict';
import test from 'node:test';
import { marketSectionFromLocation, marketSectionPath } from '../src/lib/appSectionRouting';
import {
  MATTERS_VISIBLE,
  buildWorkstationRail,
  composeMatters,
  rotationQuadrants,
  stepSymbols,
  truncationLabel,
} from '../src/sections/market/marketBriefModel';
import {
  movePanel,
  railCollapsed,
  resolveSectionLayout,
  sectionNewCounts,
  setPanelWidth,
  togglePanelHidden,
  type SectionLayoutPref,
  type SectionPanelSpec,
} from '../src/sections/market/marketWorkstationState';
import type { EvidenceItem, MorningBriefPayload, PortfolioPosition, RrgSector, WatchlistItem } from '../src/sections/market/types';

const evidence = (symbol: string, flag?: EvidenceItem['flag']): EvidenceItem => ({
  type: 'Insider',
  symbol,
  headline: `${symbol} filing`,
  source: 'SEC Form 4',
  tone: 'up',
  t: 1_700_000_000,
  flag,
});

const brief = (overrides: Partial<MorningBriefPayload> = {}): MorningBriefPayload => ({
  briefDate: '2026-09-01',
  generatedAt: '2026-09-01T14:35:00Z',
  headline: '8 new SEC filings · XLY rotated to lagging · 3 signal flips',
  newEvidence: [evidence('AAA'), evidence('BBB', 'cluster'), evidence('CCC'), evidence('DDD'), evidence('EEE'), evidence('FFF'), evidence('GGG'), evidence('HHH')],
  signalFlips: [{ symbol: 'COIN', kind: 'soft-bottoming', detail: 'soft bottoming cleared', tone: 'flat' }],
  rrgShifts: [{ symbol: 'XLY', name: 'Consumer Discretionary', fromQuadrant: 'improving', toQuadrant: 'lagging', tone: 'down' }],
  movers: [{ symbol: 'TSLA', name: 'Tesla', last: '1', changePct: 5, tone: 'up' }],
  firstSweep: false,
  ...overrides,
});

test('market sections are addressable by query and briefing owns the bare path', () => {
  assert.equal(marketSectionPath('briefing'), '/market');
  assert.equal(marketSectionPath('portfolio'), '/market?view=portfolio');
  assert.equal(marketSectionFromLocation('/market', '?view=portfolio'), 'portfolio');
  assert.equal(marketSectionFromLocation('/market/', '?view=LEDGER'), 'ledger');
  assert.equal(marketSectionFromLocation('/market', ''), null);
  assert.equal(marketSectionFromLocation('/market', '?view=nonsense'), null);
  assert.equal(marketSectionFromLocation('/market/NVDA', '?view=portfolio'), null);
});

test('matters keep the flag-first ranking and never let filings crowd out flips and rotation', () => {
  const matters = composeMatters(brief());
  assert.equal(matters[0].symbol, 'BBB', 'flagged evidence leads');
  assert.equal(matters[1].kind, 'soft-bottoming', 'signal flips come before plain filings');
  assert.equal(matters[2].kind, 'rotation');
  assert.equal(matters[2].text, 'improving → lagging');
  const shown = matters.slice(0, MATTERS_VISIBLE).map((matter) => matter.kind);
  assert.ok(shown.includes('soft-bottoming') && shown.includes('rotation'), 'the visible six include every change kind');
  assert.equal(matters.length, 10);
  assert.equal(truncationLabel(6, 10), '6 of 10 · all →');
  assert.equal(matters[0].source, `SEC Form 4 · ${new Date(1_700_000_000 * 1000).toLocaleDateString([], { month: 'short', day: 'numeric', timeZone: 'UTC' })}`);
  assert.equal(matters[1].source, 'signal flip');
});

test('rotation quadrants group every sector and keep empty quadrants present', () => {
  const sectors: RrgSector[] = [
    { symbol: 'XLK', name: 'Tech', tail: [], quadrant: 'leading' },
    { symbol: 'XLU', name: 'Utilities', tail: [], quadrant: 'lagging' },
    { symbol: 'XLE', name: 'Energy', tail: [], quadrant: 'leading' },
  ];
  const groups = rotationQuadrants(sectors);
  assert.deepEqual(groups.leading.map((sector) => sector.symbol), ['XLK', 'XLE']);
  assert.deepEqual(groups.improving, []);
  assert.deepEqual(groups.lagging.map((sector) => sector.symbol), ['XLU']);
});

test('the rail lists the watchlist, then unwatched holdings, then unwatched movers', () => {
  const items: WatchlistItem[] = [{ symbol: 'AVGO', name: 'Broadcom', value: '1', change: '-0.2%', tone: 'down', spark: [1, 2] }];
  const holdings: PortfolioPosition[] = [
    { symbol: 'AVGO', shares: 1, avgCost: 1, last: '1', pnlPct: '+1%', tone: 'up' },
    { symbol: 'VTI', shares: 1, avgCost: 1, last: '1', pnlPct: '+9.9%', tone: 'up' },
  ];
  const entries = buildWorkstationRail({ items, active: 'Core', symbols: new Set(['AVGO']) }, holdings, brief().movers);
  assert.deepEqual(entries.map((entry) => [entry.group, entry.symbol, entry.watched]), [
    ['Core', 'AVGO', true],
    ['Holdings', 'VTI', false],
    ['Movers', 'TSLA', false],
  ]);
  const symbols = entries.map((entry) => entry.symbol);
  assert.equal(stepSymbols(symbols, null, 1), 'AVGO');
  assert.equal(stepSymbols(symbols, 'AVGO', 1), 'VTI');
  assert.equal(stepSymbols(symbols, 'TSLA', 1), 'TSLA', 'stepping past the end holds');
  assert.equal(stepSymbols([], null, 1), null);
});

test('the rail starts collapsed below 1366px unless the operator has chosen', () => {
  assert.equal(railCollapsed(null, 1440), false);
  assert.equal(railCollapsed(null, 1280), true);
  assert.equal(railCollapsed(false, 1280), false);
  assert.equal(railCollapsed(true, 1920), true);
});

test('section tabs count only what the last sweep delivered after the section was opened', () => {
  const swept = brief();
  assert.deepEqual(sectionNewCounts(swept, {}), { evidence: 8, signals: 1, structure: 1 });
  const afterVisit = sectionNewCounts(swept, { evidence: '2026-09-01T15:00:00Z', signals: '2026-09-01T10:00:00Z' });
  assert.deepEqual(afterVisit, { signals: 1, structure: 1 });
  assert.deepEqual(sectionNewCounts(null, {}), {});
  assert.deepEqual(sectionNewCounts(brief({ newEvidence: [], signalFlips: [], rrgShifts: [] }), {}), {});
});

test('section layouts honour saved order, drop unknown ids, append new panels, and clamp width', () => {
  const panels: SectionPanelSpec[] = [
    { id: 'treasury', title: 'Treasury', defaultWidth: 'full', canHalf: false },
    { id: 'sector', title: 'Sector', defaultWidth: 'half', canHalf: true },
    { id: 'industry', title: 'Industry', defaultWidth: 'half', canHalf: true },
  ];
  const pref: SectionLayoutPref = { order: ['industry', 'retired', 'treasury'], hidden: ['sector'], width: { treasury: 'half', industry: 'full' } };
  const resolved = resolveSectionLayout(panels, pref);
  assert.deepEqual(resolved.map((panel) => panel.spec.id), ['industry', 'treasury', 'sector']);
  assert.equal(resolved[0].width, 'full');
  assert.equal(resolved[1].width, 'full', 'a full-only panel ignores a stored half');
  assert.equal(resolved[2].hidden, true);

  const ids = panels.map((panel) => panel.id);
  const moved = movePanel({ order: [], hidden: [], width: {} }, ids, 'industry', -1);
  assert.deepEqual(moved.order, ['treasury', 'industry', 'sector']);
  assert.deepEqual(movePanel(moved, ids, 'treasury', -1).order, moved.order, 'moving the first panel up is a no-op');
  assert.deepEqual(togglePanelHidden(togglePanelHidden(moved, 'sector'), 'sector').hidden, []);
  assert.equal(setPanelWidth(moved, 'sector', 'full').width.sector, 'full');
});
