import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeMessage } from '../src/lib/wsNormalizers';
import { useAppStore } from '../src/store/useAppStore';

test('composer tool selections are deduplicated, removable, and session scoped', () => {
  useAppStore.setState({ composerRequestedToolIds: {} });
  const store = useAppStore.getState();

  store.addComposerRequestedTool('session-a', 'market.compare');
  store.addComposerRequestedTool('session-a', 'market.compare');
  store.addComposerRequestedTool('session-a', 'market.evidence');
  store.addComposerRequestedTool('session-b', 'files.rg');

  assert.deepEqual(useAppStore.getState().composerRequestedToolIds, {
    'session-a': ['market.compare', 'market.evidence'],
    'session-b': ['files.rg'],
  });

  store.removeComposerRequestedTool('session-a', 'market.compare');
  assert.deepEqual(useAppStore.getState().composerRequestedToolIds['session-a'], ['market.evidence']);

  store.clearComposerRequestedTools('session-a');
  assert.equal(useAppStore.getState().composerRequestedToolIds['session-a'], undefined);
  assert.deepEqual(useAppStore.getState().composerRequestedToolIds['session-b'], ['files.rg']);
});

test('transcript normalization preserves requested tool metadata without changing prose', () => {
  const message = normalizeMessage(
    {
      role: 'user',
      content: 'Compare these.',
      requestedToolIds: ['market.compare', 'market.compare', ' market.evidence '],
    },
    'session-a',
    'local-user',
    'user',
    'final',
  );

  assert.equal(message.content, 'Compare these.');
  assert.deepEqual(message.requestedToolIds, ['market.compare', 'market.evidence']);
});
