import assert from 'node:assert/strict';
import test from 'node:test';

import { useAppStore } from '../src/store/useAppStore';

test('mobile UI state starts closed and can be toggled explicitly', () => {
  const state = useAppStore.getState() as any;

  assert.equal(state.mobileOverflowOpen, false);
  assert.equal(state.mobileSessionsOpen, false);
  assert.equal(state.mobileInspectorOpen, false);
  assert.equal(state.mobileMemeHistoryOpen, false);
  assert.equal(state.mobileMemeKeepersOpen, false);
  assert.equal(state.memeLabSeedAsset, null);

  state.setMobileOverflowOpen(true);
  state.setMobileSessionsOpen(true);
  state.setMobileInspectorOpen(true);
  state.setMobileMemeHistoryOpen(true);
  state.setMobileMemeKeepersOpen(true);
  state.setMemeLabSeedAsset({ assetId: 'media-1' });

  const next = useAppStore.getState() as any;
  assert.equal(next.mobileOverflowOpen, true);
  assert.equal(next.mobileSessionsOpen, true);
  assert.equal(next.mobileInspectorOpen, true);
  assert.equal(next.mobileMemeHistoryOpen, true);
  assert.equal(next.mobileMemeKeepersOpen, true);
  assert.equal(next.memeLabSeedAsset.assetId, 'media-1');
});
