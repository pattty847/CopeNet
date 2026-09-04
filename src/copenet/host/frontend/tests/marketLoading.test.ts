import assert from 'node:assert/strict';
import test from 'node:test';
import { PORTFOLIO_PANELS, SIGNAL_PANELS, STRUCTURE_PANELS } from '../src/sections/market/marketSectionPanels';
import { resolveSectionLayout, type SectionPanelSpec } from '../src/sections/market/marketWorkstationState';
import { observedPanelData } from '../src/sections/market/marketBriefModel';

test('initial server placeholders are unavailable, while genuine zero observations stay visible', () => {
  assert.equal(observedPanelData(undefined), null);
  assert.equal(observedPanelData({ status: 'preview', data: { vix: 0 } }), null);
  assert.deepEqual(observedPanelData({ status: 'live', data: { breadthPct: 0 } }), { breadthPct: 0 });
  assert.deepEqual(observedPanelData({ status: 'stale', data: { vix: 20 } }), { vix: 20 });
});

test('market loading and loaded panels share one complete set of panel identities', () => {
  for (const specs of [STRUCTURE_PANELS, SIGNAL_PANELS, PORTFOLIO_PANELS]) {
    assert.deepEqual(
      Object.keys(specs),
      Object.values(specs).map((panel) => panel.id),
    );
  }
  assert.equal(PORTFOLIO_PANELS.tradeHistory.defaultWidth, 'full');
  assert.equal(PORTFOLIO_PANELS.allTimePnl.defaultWidth, 'half');
});

test('shared signal panel specs restore desktop ordering, hiding and widths', () => {
  const panels: SectionPanelSpec[] = Object.values(SIGNAL_PANELS);
  const pref = { order: ['trend', 'softBottoming'], hidden: ['accumulation'], width: { trend: 'full' as const } };
  const resolved = resolveSectionLayout(panels, pref).filter((panel) => !panel.hidden);
  assert.deepEqual(
    resolved.map((panel) => [panel.spec.id, panel.width]),
    [
      ['trend', 'full'],
      ['softBottoming', 'full'],
    ],
  );
});

test('mobile loading ignores desktop panel hiding and restores the complete stacked layout', () => {
  const panels: SectionPanelSpec[] = Object.values(PORTFOLIO_PANELS);
  const pref = { order: ['tradeHistory'], hidden: ['positions'], width: { tradeHistory: 'half' as const } };
  const resolved = resolveSectionLayout(panels, pref, true);
  assert.deepEqual(
    resolved.map((panel) => panel.spec.id),
    Object.keys(PORTFOLIO_PANELS),
  );
  assert.ok(resolved.every((panel) => panel.width === 'full' && !panel.hidden));
});
