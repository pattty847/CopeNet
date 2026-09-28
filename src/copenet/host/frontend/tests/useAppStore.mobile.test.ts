import assert from 'node:assert/strict';
import test from 'node:test';

import { useAppStore } from '../src/store/useAppStore';

test('mobile UI state starts closed and can be toggled explicitly', () => {
  const state = useAppStore.getState() as any;

  assert.equal(state.mobileOverflowOpen, false);
  assert.equal(state.mobileSessionsOpen, false);
  assert.equal(state.mobileInspectorOpen, false);

  state.setMobileOverflowOpen(true);
  state.setMobileSessionsOpen(true);
  state.setMobileInspectorOpen(true);

  const next = useAppStore.getState() as any;
  assert.equal(next.mobileOverflowOpen, true);
  assert.equal(next.mobileSessionsOpen, true);
  assert.equal(next.mobileInspectorOpen, true);
});
