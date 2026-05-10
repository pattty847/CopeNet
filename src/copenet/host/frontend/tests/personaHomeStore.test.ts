import assert from 'node:assert/strict';
import test from 'node:test';

import { useAppStore } from '../src/store/useAppStore';

test('persona home state tracks settings and session usage', () => {
  const state = useAppStore.getState() as any;

  state.setPersonaHome({
    personaId: 'default',
    personaFlavorId: 'codex-cli/gpt-5.4',
    personaPrivacyTier: 'private',
    active: true,
    rootDir: '/tmp/personas',
    loadedFiles: ['/tmp/personas/default/core/SOUL.md'],
  });
  state.setPersonaSettings({
    defaultPersonaId: 'default',
    defaultPrivacyTier: 'safe',
    modelOverrides: {
      'codex-cli:gpt-5.4': {
        personaId: 'default',
        flavorId: 'codex-cli/gpt-5.4',
      },
    },
  });
  state.setSessionIdentityUsage('session-alpha', {
    profileActive: true,
    memoryCount: 1,
    memoryItemIds: ['memory-1'],
    personaActive: true,
    personaId: 'default',
    personaFlavorId: 'codex-cli/gpt-5.4',
    personaPrivacyTier: 'private',
  });

  const next = useAppStore.getState() as any;
  assert.equal(next.personaHome.personaFlavorId, 'codex-cli/gpt-5.4');
  assert.equal(next.personaSettings.defaultPrivacyTier, 'safe');
  assert.equal(next.sessionIdentityUsage['session-alpha'].personaPrivacyTier, 'private');
});
