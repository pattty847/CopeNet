import assert from 'node:assert/strict';
import test from 'node:test';

import { cycleHomeCardSize, DEFAULT_HOME_LAYOUT, normalizeHomeLayout, reorderHomeLayout } from '../src/components/home/homeLayout';

test('normalizeHomeLayout restores missing cards and ignores unknown ones', () => {
  const layout = normalizeHomeLayout([
    { id: 'hero', span: 12, height: 'regular' },
    { id: 'unknown-card', span: 4, height: 'compact' },
  ]);

  assert.equal(layout[0]?.id, 'hero');
  assert.ok(layout.length >= DEFAULT_HOME_LAYOUT.length);
  assert.ok(layout.some((item) => item.id === 'memory_profile'));
});

test('reorderHomeLayout moves the dragged card before the drop target', () => {
  const next = reorderHomeLayout(DEFAULT_HOME_LAYOUT, 'system_health', 'hero');
  assert.equal(next[0]?.id, 'system_health');
  assert.equal(next[1]?.id, 'hero');
});

test('cycleHomeCardSize snaps width and height to allowed values', () => {
  const grownSpan = cycleHomeCardSize(DEFAULT_HOME_LAYOUT, 'system_health', 'grow', 'span');
  const systemHealth = grownSpan.find((item) => item.id === 'system_health');
  assert.equal(systemHealth?.span, 6);

  const tallerHero = cycleHomeCardSize(DEFAULT_HOME_LAYOUT, 'hero', 'grow', 'height');
  const hero = tallerHero.find((item) => item.id === 'hero');
  assert.equal(hero?.height, 'tall');
});
