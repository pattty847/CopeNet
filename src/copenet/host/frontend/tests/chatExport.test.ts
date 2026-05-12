import test from 'node:test';
import assert from 'node:assert/strict';

import type { Message, Session, SessionRunRecord } from '../src/types/backend';
import { formatConversationMarkdown, formatConversationWithToolActivityMarkdown } from '../src/lib/chatExport';

function makeMessage(partial: Partial<Message> & Pick<Message, 'localId' | 'role' | 'content' | 'timestamp'>): Message {
  return {
    sessionKey: 'session-1',
    runId: null,
    provider: null,
    model: null,
    providerSessionId: null,
    state: 'final',
    toolExecution: null,
    errorMessage: null,
    optimistic: false,
    ...partial,
  };
}

function makeSession(partial: Partial<Session> = {}): Session {
  return {
    key: 'session-1',
    sessionId: 'session-1',
    title: 'Astronomy Notes',
    provider: 'openai-codex',
    model: 'gpt-5.5',
    systemPromptId: 'default',
    taskPromptId: 'none',
    personaId: 'default',
    personaFlavorId: null,
    personaPrivacyTier: 'private',
    workspaceRoot: '/tmp/workspace',
    archived: false,
    providerSessionId: null,
    createdAt: '2026-05-10T23:13:00.000Z',
    updatedAt: '2026-05-10T23:14:00.000Z',
    lastRunId: null,
    inFlightRunId: null,
    ...partial,
  };
}

function makeRun(partial: Partial<SessionRunRecord> = {}): SessionRunRecord {
  return {
    runId: 'run-1',
    sessionKey: 'session-1',
    provider: 'openai-codex',
    model: 'gpt-5.5',
    status: 'completed',
    userMessage: 'Investigate Kepler',
    toolExecutionMode: 'batch',
    willAttemptToolLoop: true,
    startedAt: '2026-05-10T23:13:00.000Z',
    completedAt: '2026-05-10T23:14:00.000Z',
    workingSet: {},
    toolSteps: [],
    artifactIds: [],
    outputSummary: 'Summarized the findings.',
    error: null,
    metadata: {},
    ...partial,
  };
}

test('formatConversationMarkdown formats user and assistant messages with metadata', () => {
  const markdown = formatConversationMarkdown({
    session: makeSession(),
    messages: [
      makeMessage({ localId: 'm1', role: 'user', content: 'What changed in persona home?', timestamp: '2026-05-10T23:13:00.000Z' }),
      makeMessage({ localId: 'm2', role: 'assistant', content: 'We added slash commands and a panel.', timestamp: '2026-05-10T23:14:00.000Z' }),
    ],
    providerLabel: 'OpenAI Codex',
    modelLabel: 'gpt-5.5',
  });

  assert.match(markdown, /^# CopeNet Chat Export/m);
  assert.match(markdown, /^Session: Astronomy Notes$/m);
  assert.match(markdown, /^Provider: OpenAI Codex$/m);
  assert.match(markdown, /^Model: gpt-5.5$/m);
  assert.match(markdown, /^## User — /m);
  assert.match(markdown, /^What changed in persona home\?$/m);
  assert.match(markdown, /^## Assistant — /m);
  assert.match(markdown, /^We added slash commands and a panel\.$/m);
});

test('formatConversationMarkdown skips system messages and empty content', () => {
  const markdown = formatConversationMarkdown({
    session: makeSession({ title: null }),
    messages: [
      makeMessage({ localId: 'sys', role: 'system', content: 'internal note', timestamp: '2026-05-10T23:10:00.000Z' }),
      makeMessage({ localId: 'blank', role: 'assistant', content: '   ', timestamp: '2026-05-10T23:11:00.000Z' }),
      makeMessage({ localId: 'user', role: 'user', content: 'Keep only this', timestamp: '2026-05-10T23:12:00.000Z' }),
    ],
    providerLabel: 'OpenAI Codex',
    modelLabel: 'gpt-5.5',
  });

  assert.doesNotMatch(markdown, /internal note/);
  assert.doesNotMatch(markdown, /## System —/);
  assert.match(markdown, /^Session: session-1$/m);
  assert.match(markdown, /^Keep only this$/m);
});

test('formatConversationWithToolActivityMarkdown appends readable tool activity', () => {
  const markdown = formatConversationWithToolActivityMarkdown({
    session: makeSession(),
    messages: [
      makeMessage({ localId: 'm1', role: 'user', content: 'Read the Kepler notes', timestamp: '2026-05-10T23:13:00.000Z' }),
      makeMessage({ localId: 'm2', role: 'assistant', content: 'I checked the notes and found the key thread.', timestamp: '2026-05-10T23:14:00.000Z' }),
    ],
    runs: [
      makeRun({
        toolSteps: [
          {
            toolId: 'files.read',
            ok: true,
            summary: 'Read README.md',
            target: '/tmp/workspace/README.md',
          },
          {
            toolId: 'tool.batch',
            ok: true,
            summary: 'Read 2 files',
            members: [
              {
                callId: 'call-2',
                toolId: 'files.read',
                ok: true,
                summary: 'Read docs/kepler.md',
                target: '/tmp/workspace/docs/kepler.md',
              },
              {
                callId: 'call-3',
                toolId: 'files.read',
                ok: false,
                summary: 'Read docs/blocked.md',
                target: '/tmp/workspace/docs/blocked.md',
                error: 'permission denied',
              },
            ],
          },
        ],
      }),
    ],
    providerLabel: 'OpenAI Codex',
    modelLabel: 'gpt-5.5',
  });

  assert.match(markdown, /^# Tool Activity$/m);
  assert.match(markdown, /^## Run — /m);
  assert.match(markdown, /Prompt: Investigate Kepler/);
  assert.ok(markdown.includes('- `files.read` — Read README.md'));
  assert.ok(markdown.includes('Target: `/tmp/workspace/README.md`'));
  assert.ok(markdown.includes('- `files.read` — Read docs/kepler.md'));
  assert.ok(markdown.includes('- `files.read` — Read docs/blocked.md'));
  assert.match(markdown, /Error: permission denied/);
  assert.ok(markdown.includes('Output summary: Summarized the findings.'));
});
