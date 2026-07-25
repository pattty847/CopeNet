import assert from 'node:assert/strict';
import test from 'node:test';

import { useAppStore } from '../src/store/useAppStore';
import { abortActiveRunAction } from '../src/lib/wsChatActions';
import { handleChatEventAction } from '../src/lib/wsChatEvents';
import type { ApprovalRequest, Session } from '../src/types/backend';

function session(key: string, inFlightRunId: string | null): Session {
  return {
    key,
    sessionId: key,
    title: key,
    provider: 'openai-codex',
    model: 'gpt-5.5',
    systemPromptId: 'default',
    taskPromptId: 'none',
    personaId: 'default',
    personaFlavorId: null,
    personaPrivacyTier: 'private',
    workspaceRoot: null,
    archived: false,
    providerSessionId: null,
    createdAt: '2026-07-17T00:00:00Z',
    updatedAt: '2026-07-17T00:00:00Z',
    lastRunId: null,
    inFlightRunId,
  };
}

function approval(approvalId: string, sessionKey: string, runId: string): ApprovalRequest {
  return {
    approvalId,
    sessionKey,
    runId,
    status: 'pending',
    actionClass: 'process_execution',
    toolId: 'shell.exec',
    proposedAction: { description: 'Run a command' },
    rationale: null,
    createdAt: '2026-07-17T00:00:00Z',
    resolvedAt: null,
    outcome: null,
  };
}

test('active runs and live tool calls remain isolated across sessions', () => {
  useAppStore.setState({
    activeRunsBySession: {},
    liveToolCallsByRun: {},
    lastTurnStateBySession: {},
  });
  const store = useAppStore.getState();

  store.setActiveRun('session-a', 'run-a');
  store.setActiveRun('session-b', 'run-b');
  store.pushLiveToolCall('run-a', {
    id: 'call-a',
    toolId: 'market.ticker',
    state: 'running',
    summary: 'Reading AAPL',
    error: null,
    startedAt: '2026-07-17T00:00:00Z',
    completedAt: null,
  });

  let next = useAppStore.getState();
  assert.deepEqual(next.activeRunsBySession, { 'session-a': 'run-a', 'session-b': 'run-b' });
  assert.equal(next.liveToolCallsByRun['run-a']?.[0]?.toolId, 'market.ticker');
  assert.equal(next.liveToolCallsByRun['run-b'], undefined);

  store.clearActiveRun('session-a', 'run-a');
  next = useAppStore.getState();
  assert.deepEqual(next.activeRunsBySession, { 'session-b': 'run-b' });
});

test('bootstrap run reconciliation replaces stale client state with server truth', () => {
  useAppStore.setState({ activeRunsBySession: { stale: 'stale-run' } });
  useAppStore.getState().syncActiveRuns([
    session('session-a', 'run-a'),
    session('session-b', null),
    session('session-c', 'run-c'),
  ]);

  assert.deepEqual(useAppStore.getState().activeRunsBySession, {
    'session-a': 'run-a',
    'session-c': 'run-c',
  });
});

test('resolving one approval preserves another session approval', () => {
  useAppStore.setState({ pendingApprovalsById: {}, approvalHistory: [] });
  const store = useAppStore.getState();
  store.setPendingApprovals([
    approval('approval-a', 'session-a', 'run-a'),
    approval('approval-b', 'session-b', 'run-b'),
  ]);
  store.resolveApproval('approval-a', {
    decision: 'approved',
    decidedAt: '2026-07-17T00:01:00Z',
  });

  const next = useAppStore.getState();
  assert.equal(next.pendingApprovalsById['approval-a'], undefined);
  assert.equal(next.pendingApprovalsById['approval-b']?.sessionKey, 'session-b');
  assert.equal(next.approvalHistory.find((item) => item.approvalId === 'approval-a')?.status, 'approved');
});

test('abort sends an explicit matching session and run pair', async () => {
  let observedMethod = '';
  let observedParams: Record<string, unknown> = {};
  const request = async (method: string, params: Record<string, unknown>) => {
    observedMethod = method;
    observedParams = params;
    return {};
  };

  await abortActiveRunAction(request as never, 'session-b', 'run-b');

  assert.equal(observedMethod, 'chat.abort');
  assert.deepEqual(observedParams, { sessionKey: 'session-b', runId: 'run-b' });
});

test('a final event clears only the run owned by its session', () => {
  useAppStore.setState({
    activeRunsBySession: { 'session-a': 'run-a', 'session-b': 'run-b' },
    pendingAssistants: {},
  });

  handleChatEventAction(
    { sessionKey: 'session-a', runId: 'run-a', seq: 4, state: 'final' },
    async () => {},
    async () => {},
  );

  assert.deepEqual(useAppStore.getState().activeRunsBySession, { 'session-b': 'run-b' });
});
