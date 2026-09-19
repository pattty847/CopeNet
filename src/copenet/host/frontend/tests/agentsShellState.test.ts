import assert from 'node:assert/strict';
import test from 'node:test';

import { wsClient } from '../src/lib/wsClient';
import { useAppStore } from '../src/store/useAppStore';

test('agents shell defaults to collapsed global rail with sessions panel closed', () => {
  const state = useAppStore.getState() as any;

  assert.equal(state.primaryNavCollapsed, true);
  assert.equal(state.sessionsPanelOpen, false);
});

test('beginDraft closes the sessions panel and clears the inspector target', () => {
  const state = useAppStore.getState() as any;
  state.setSessionsPanelOpen(true);
  state.setInspectorTarget({ kind: 'artifact', artifactId: 'artifact-123' });

  wsClient.beginDraft();

  const next = useAppStore.getState() as any;
  assert.equal(next.draftOpen, true);
  assert.equal(next.sessionsPanelOpen, false);
  assert.equal(next.inspectorTarget, null);
});
