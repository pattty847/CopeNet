import assert from 'node:assert/strict';
import test from 'node:test';

import { useAppStore } from '../src/store/useAppStore';

function makeStorage() {
  const values = new Map<string, string>();
  return {
    getItem(key: string) {
      return values.has(key) ? values.get(key)! : null;
    },
    setItem(key: string, value: string) {
      values.set(key, value);
    },
    removeItem(key: string) {
      values.delete(key);
    },
    clear() {
      values.clear();
    },
  };
}

test('draft runtime preference persists provider and model selections', () => {
  const previousWindow = (globalThis as { window?: unknown }).window;
  const localStorage = makeStorage();
  (globalThis as { window?: unknown }).window = { localStorage };

  try {
    useAppStore.getState().replaceDraftSettings({
      provider: 'openai-codex',
      model: 'gpt-5.5',
      systemPromptId: 'friendly',
      taskPromptId: 'none',
      personaId: 'default',
      personaFlavorId: '',
      personaPrivacyTier: 'private',
      workspaceRoot: '',
    });

    let stored = JSON.parse(localStorage.getItem('copenet.draftRuntime') || '{}');
    assert.equal(stored.provider, 'openai-codex');
    assert.equal(stored.model, 'gpt-5.5');

    useAppStore.getState().patchDraftSettings({ provider: 'claude-cli', model: 'claude-sonnet-4' });
    stored = JSON.parse(localStorage.getItem('copenet.draftRuntime') || '{}');
    assert.equal(stored.provider, 'claude-cli');
    assert.equal(stored.model, 'claude-sonnet-4');
  } finally {
    if (previousWindow === undefined) {
      delete (globalThis as { window?: unknown }).window;
    } else {
      (globalThis as { window?: unknown }).window = previousWindow;
    }
  }
});
