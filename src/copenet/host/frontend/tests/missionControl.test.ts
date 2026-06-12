import assert from 'node:assert/strict';
import test from 'node:test';

import { buildMissionControlItems, type MissionControlInput } from '../src/lib/missionControl';
import type { ApprovalRequest, Session, SessionRunRecord, SessionStateRecord } from '../src/types/backend';

const NOW = '2026-05-15T16:00:00.000Z';

function session(overrides: Partial<Session>): Session {
  return {
    key: 'session-1',
    sessionId: 'session-1',
    title: 'CopeNet Core',
    provider: 'openai-codex',
    model: 'gpt-5.4',
    systemPromptId: 'default',
    taskPromptId: 'full-access',
    personaId: null,
    personaFlavorId: null,
    personaPrivacyTier: null,
    workspaceRoot: '/repo',
    archived: false,
    providerSessionId: null,
    createdAt: '2026-05-15T12:00:00.000Z',
    updatedAt: '2026-05-15T15:30:00.000Z',
    lastRunId: null,
    inFlightRunId: null,
    ...overrides,
  };
}

function run(overrides: Partial<SessionRunRecord>): SessionRunRecord {
  return {
    runId: 'run-1',
    sessionKey: 'session-1',
    provider: 'openai-codex',
    model: 'gpt-5.4',
    status: 'completed',
    userMessage: 'Improve the console',
    toolExecutionMode: 'auto',
    willAttemptToolLoop: true,
    startedAt: '2026-05-15T15:00:00.000Z',
    completedAt: '2026-05-15T15:03:00.000Z',
    workingSet: {},
    toolSteps: [],
    artifactIds: [],
    outputSummary: 'Finished the pass.',
    error: null,
    metadata: {},
    ...overrides,
  };
}

function state(overrides: Partial<SessionStateRecord>): SessionStateRecord {
  return {
    session_key: 'session-1',
    task_summary: 'Tighten the Agents console',
    goals: [],
    active_entities: [],
    working_set_refs: [],
    constraints: [],
    unresolved_questions: [],
    prior_decisions: [],
    plan_snapshot: {},
    relevant_asset_ids: [],
    relevant_artifact_ids: [],
    created_at: '2026-05-15T12:00:00.000Z',
    updated_at: '2026-05-15T15:10:00.000Z',
    ...overrides,
  };
}

function approval(overrides: Partial<ApprovalRequest>): ApprovalRequest {
  return {
    approvalId: 'approval-1',
    runId: 'run-approval',
    sessionKey: 'session-1',
    status: 'pending',
    actionClass: 'filesystem_write',
    toolId: 'files.write',
    proposedAction: { description: 'Write a file', target: '/repo/file.ts' },
    rationale: 'The agent needs permission.',
    createdAt: '2026-05-15T15:40:00.000Z',
    resolvedAt: null,
    outcome: null,
    ...overrides,
  };
}

function build(input: Partial<MissionControlInput>) {
  return buildMissionControlItems({
    sessions: [],
    sessionStates: {},
    runsBySession: {},
    approvals: [],
    now: NOW,
    ...input,
  });
}

test('buildMissionControlItems promotes pending approvals to needs attention', () => {
  const items = build({
    sessions: [session({})],
    approvals: [approval({})],
  });

  assert.equal(items[0]?.lane, 'needs_attention');
  assert.equal(items[0]?.kind, 'approval');
  assert.equal(items[0]?.sessionKey, 'session-1');
  assert.match(items[0]?.title || '', /Approval needed/);
});

test('buildMissionControlItems promotes failed runs to needs attention', () => {
  const items = build({
    sessions: [session({ key: 'session-2', title: 'Provider probe' })],
    runsBySession: {
      'session-2': [
        run({
          runId: 'run-failed',
          sessionKey: 'session-2',
          status: 'failed',
          error: 'Provider exited early',
          outputSummary: '',
        }),
      ],
    },
  });

  assert.equal(items[0]?.lane, 'needs_attention');
  assert.equal(items[0]?.kind, 'failed_run');
  assert.equal(items[0]?.runId, 'run-failed');
  assert.match(items[0]?.detail || '', /Provider exited early/);
});

test('buildMissionControlItems identifies successful tool-heavy runs as recently useful', () => {
  const items = build({
    sessions: [session({})],
    runsBySession: {
      'session-1': [
        run({
          runId: 'run-useful',
          toolSteps: [
            { toolId: 'files.read', ok: true, summary: 'Read file' },
            { toolId: 'repo.search', ok: true, summary: 'Searched repo' },
          ],
          artifactIds: ['artifact-1'],
        }),
      ],
    },
  });

  assert.equal(items[0]?.lane, 'recently_useful');
  assert.equal(items[0]?.kind, 'useful_run');
  assert.match(items[0]?.meta, /2 tools/);
});

test('buildMissionControlItems turns stale sessions with open questions into resume items', () => {
  const items = build({
    sessions: [
      session({
        updatedAt: '2026-05-14T12:00:00.000Z',
      }),
    ],
    sessionStates: {
      'session-1': state({
        updated_at: '2026-05-14T12:00:00.000Z',
        unresolved_questions: ['Which provider should own the run?'],
      }),
    },
  });

  assert.equal(items[0]?.lane, 'ready_to_continue');
  assert.equal(items[0]?.kind, 'resume_session');
  assert.match(items[0]?.detail || '', /Which provider should own the run/);
});

test('buildMissionControlItems suggests workflow promotion for repeated tool-heavy sessions', () => {
  const items = build({
    sessions: [session({ key: 'session-workflow', title: 'Weekly probe' })],
    sessionStates: {
      'session-workflow': state({
        session_key: 'session-workflow',
        task_summary: 'Run the weekly provider comparison',
      }),
    },
    runsBySession: {
      'session-workflow': [
        run({
          runId: 'run-a',
          sessionKey: 'session-workflow',
          toolSteps: [
            { toolId: 'repo.search', ok: true, summary: 'Searched' },
            { toolId: 'files.read', ok: true, summary: 'Read' },
          ],
        }),
        run({
          runId: 'run-b',
          sessionKey: 'session-workflow',
          toolSteps: [
            { toolId: 'repo.search', ok: true, summary: 'Searched again' },
            { toolId: 'files.read', ok: true, summary: 'Read again' },
          ],
        }),
      ],
    },
  });

  assert.equal(items[0]?.lane, 'promote_to_workflow');
  assert.equal(items[0]?.kind, 'workflow_candidate');
  assert.match(items[0]?.title || '', /Promote/);
});

test('buildMissionControlItems excludes archived sessions', () => {
  const items = build({
    sessions: [session({ archived: true })],
    approvals: [approval({})],
    runsBySession: {
      'session-1': [run({ status: 'failed', error: 'Nope' })],
    },
  });

  assert.equal(items.length, 0);
});
