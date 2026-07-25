import assert from 'node:assert/strict';
import test from 'node:test';

import { useAppStore } from '../src/store/useAppStore';

test('memory state can be updated and identity usage tracked per session', () => {
  const state = useAppStore.getState() as any;

  state.setMemoryItems([
    {
      id: 'memory-1',
      category: 'preference',
      title: 'Chat vibe',
      summary: 'Keep it warm and direct.',
      detail: null,
      tags: ['tone'],
      source: 'explicit',
      confidence: 0.9,
      createdAt: '2026-05-09T00:00:00Z',
      updatedAt: '2026-05-09T00:00:00Z',
      archived: false,
      lastSessionKey: null,
    },
  ]);
  state.setSessionIdentityUsage('session-alpha', {
    profileActive: true,
    memoryCount: 1,
    memoryItemIds: ['memory-1'],
  });
  state.setLastMemoryChange({
    item: {
      id: 'memory-1',
      category: 'preference',
      title: 'Chat vibe',
      summary: 'Keep it warm and direct.',
      detail: null,
      tags: ['tone'],
      source: 'explicit',
      confidence: 0.9,
      createdAt: '2026-05-09T00:00:00Z',
      updatedAt: '2026-05-09T00:00:00Z',
      archived: false,
      lastSessionKey: 'session-alpha',
    },
    reason: 'run_extraction',
    sessionKey: 'session-alpha',
    runId: 'run-1',
  });

  const next = useAppStore.getState() as any;
  assert.equal(next.memoryItems.length, 1);
  assert.equal(next.sessionIdentityUsage['session-alpha'].memoryCount, 1);
  assert.equal(next.lastMemoryChange.reason, 'run_extraction');

  state.upsertMemoryItem({
    id: 'memory-1',
    category: 'preference',
    title: 'Chat vibe',
    summary: 'Keep it playful and warm.',
    detail: null,
    tags: ['tone'],
    source: 'session_observation',
    confidence: 0.92,
    createdAt: '2026-05-09T00:00:00Z',
    updatedAt: '2026-05-09T01:00:00Z',
    archived: false,
    lastSessionKey: 'session-alpha',
  });

  assert.equal(useAppStore.getState().memoryItems[0]?.summary, 'Keep it playful and warm.');
});
