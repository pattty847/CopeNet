import assert from 'node:assert/strict';
import test from 'node:test';

import { organizeSessionDrawerSections } from '../src/lib/sessionDrawer';
import type { Session } from '../src/types/backend';

const now = new Date('2026-05-07T21:00:00.000Z');

function makeSession(overrides: Partial<Session>): Session {
  return {
    key: overrides.key || 'sess',
    sessionId: overrides.sessionId || `session-${overrides.key || 'sess'}`,
    title: overrides.title || 'Untitled',
    provider: overrides.provider || 'codex-cli',
    model: overrides.model || 'gpt-5.4',
    systemPromptId: overrides.systemPromptId || 'default',
    taskPromptId: overrides.taskPromptId || 'none',
    personaId: overrides.personaId || 'default',
    personaFlavorId: overrides.personaFlavorId || null,
    personaPrivacyTier: overrides.personaPrivacyTier || 'private',
    providerSessionId: overrides.providerSessionId || null,
    createdAt: overrides.createdAt || now.toISOString(),
    updatedAt: overrides.updatedAt || now.toISOString(),
    archived: overrides.archived || false,
    workspaceRoot: overrides.workspaceRoot || '',
    lastRunId: overrides.lastRunId || null,
    inFlightRunId: overrides.inFlightRunId || null,
  };
}

test('organizeSessionDrawerSections separates pinned and recent buckets by recency', () => {
  const sections = organizeSessionDrawerSections({
    sessions: [
      makeSession({ key: 'today-1', title: 'Today', updatedAt: '2026-05-07T18:00:00.000Z' }),
      makeSession({ key: 'week-1', title: 'This Week', updatedAt: '2026-05-05T15:00:00.000Z' }),
      makeSession({ key: 'earlier-1', title: 'Earlier', updatedAt: '2026-04-20T12:00:00.000Z' }),
      makeSession({ key: 'pinned-1', title: 'Pinned', updatedAt: '2026-05-01T12:00:00.000Z' }),
      makeSession({ key: 'archived-1', title: 'Archived', archived: true, updatedAt: '2026-05-07T19:00:00.000Z' }),
    ],
    pinnedSessionKeys: ['pinned-1'],
    query: '',
    now,
  });

  assert.deepEqual(sections.pinned.map((session) => session.key), ['pinned-1']);
  assert.deepEqual(sections.recent.today.map((session) => session.key), ['today-1']);
  assert.deepEqual(sections.recent.thisWeek.map((session) => session.key), ['week-1']);
  assert.deepEqual(sections.recent.earlier.map((session) => session.key), ['earlier-1']);
  assert.deepEqual(sections.archived.map((session) => session.key), ['archived-1']);
});
