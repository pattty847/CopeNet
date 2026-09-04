import assert from 'node:assert/strict';
import test from 'node:test';
import { sendMessageToSessionAction } from '../src/lib/wsChatActions';
import { useAppStore } from '../src/store/useAppStore';
import type { Session } from '../src/types/backend';

const session: Session = {
  key: 'market-session', sessionId: 'market-session', title: 'Market', provider: 'openai-codex', model: 'test',
  systemPromptId: null, taskPromptId: 'none', personaId: null, personaFlavorId: null, personaPrivacyTier: null,
  workspaceRoot: null, archived: false, providerSessionId: null, createdAt: '', updatedAt: '', lastRunId: null, inFlightRunId: null,
};
const options = {
  session, message: 'Inspect this candle', idempotencyKey: 'chart-run', displayContext: { symbol: 'TEST', timeframe: 'D' as const },
  marketContext: { observationId: 'observation', documentId: 'document', viewId: 'view', detail: 'balanced' as const, access: 'annotate' as const },
};

test('Market send and lost-response retry preserve Agents selection and streaming assistant', async () => {
  useAppStore.setState({ activeSessionKey: 'agents-session', messages: {}, sessions: [session], activeRunsBySession: {}, liveToolCallsByRun: {} });
  const calls: Record<string, unknown>[] = [];
  const request = async <T extends Record<string, unknown>>(_method: string, params: Record<string, unknown>) => {
    calls.push(params);
    return { runId: 'chart-run', status: calls.length === 1 ? 'started' : 'in_flight' } as unknown as T;
  };
  await sendMessageToSessionAction(request, options);
  const assistant = useAppStore.getState().messages[session.key].find((message) => message.role === 'assistant')!;
  useAppStore.getState().updateMessage(session.key, assistant.localId, { content: 'Already streaming' });
  await sendMessageToSessionAction(request, options);
  const state = useAppStore.getState();
  assert.equal(state.activeSessionKey, 'agents-session');
  assert.equal(state.messages[session.key].length, 2);
  assert.equal(state.messages[session.key][1].content, 'Already streaming');
  assert.equal(state.messages['agents-session'], undefined);
  assert.deepEqual(calls[0].marketContext, options.marketContext);
  assert.equal(state.messages[session.key][0].marketContext?.symbol, 'TEST');
  assert.equal(state.messages[session.key][0].marketContext?.timeframe, 'D');
  assert.equal(calls[0].idempotencyKey, calls[1].idempotencyKey);
});

test('A failed chart send stays on its captured session after navigation', async () => {
  useAppStore.setState({ activeSessionKey: 'agents-session', messages: {}, sessions: [session] });
  const request = async <T extends Record<string, unknown>>(): Promise<T> => {
    useAppStore.getState().setActiveSessionKey('another-agents-session');
    throw new Error('Capture unavailable');
  };
  await assert.rejects(sendMessageToSessionAction(request, options), /Capture unavailable/);
  const state = useAppStore.getState();
  assert.equal(state.activeSessionKey, 'another-agents-session');
  assert.equal(state.messages[session.key].at(-1)?.errorMessage, 'Capture unavailable');
  assert.equal(state.messages['another-agents-session'], undefined);
});

test('A complete tool turn arriving before chat.send resolves remains visible', async () => {
  const { handleChatEventAction } = await import('../src/lib/wsChatEvents');
  useAppStore.setState({ activeSessionKey: 'agents-session', messages: {}, sessions: [session], pendingAssistants: {}, activeRunsBySession: {} });
  const request = async <T extends Record<string, unknown>>(): Promise<T> => {
    handleChatEventAction({ sessionKey: session.key, runId: 'chart-run', seq: 1, state: 'tool_called', toolCall: { toolId: 'market.chart.read', callId: 'read-1', arguments: {} } }, async () => undefined, async () => undefined);
    handleChatEventAction({ sessionKey: session.key, runId: 'chart-run', seq: 2, state: 'final', message: { role: 'assistant', content: 'The captured low is 9.' } }, async () => undefined, async () => undefined);
    return { runId: 'chart-run', status: 'started' } as unknown as T;
  };
  await sendMessageToSessionAction(request, options);
  const state = useAppStore.getState();
  const assistant = state.messages[session.key].find((message) => message.role === 'assistant')!;
  assert.equal(assistant.content, 'The captured low is 9.');
  assert.equal(assistant.state, 'final');
  assert.equal(state.pendingAssistants['chart-run'], undefined);
  assert.equal(state.activeRunsBySession[session.key], undefined);
});

test('An older history response cannot erase a newer chart send', async () => {
  const { loadHistoryAction } = await import('../src/lib/wsSessionActions');
  useAppStore.setState({ activeSessionKey: 'agents-session', messages: {}, sessions: [session], pendingAssistants: {}, activeRunsBySession: {} });
  let finishHistory!: (payload: Record<string, unknown>) => void;
  const history = loadHistoryAction(async <T extends Record<string, unknown>>() => new Promise<Record<string, unknown>>((resolve) => { finishHistory = resolve; }) as Promise<T>, session.key);
  await sendMessageToSessionAction(async <T extends Record<string, unknown>>() => ({ runId: 'chart-run', status: 'started' }) as unknown as T, options);
  finishHistory({ sessionKey: session.key, messages: [] });
  await history;
  const state = useAppStore.getState();
  assert.equal(state.messages[session.key].length, 2);
  assert.equal(state.messages[session.key][1].localId, state.pendingAssistants['chart-run'].localId);
});

test('Lost first-session creation resolves the stable key without changing Agents selection', async () => {
  const { createMarketChartApi } = await import('../src/lib/wsMarketChart');
  const existing = { ...session, personaPrivacyTier: 'off' as const };
  const settings = { ...useAppStore.getState().draftSettings, provider: existing.provider, model: 'test',
    systemPromptId: '', taskPromptId: 'none', personaId: '', personaFlavorId: '', personaPrivacyTier: 'off' as const, workspaceRoot: '' };
  const methods: string[] = [];
  useAppStore.setState({ activeSessionKey: 'agents-session', sessions: [] });
  const api = createMarketChartApi(async <T extends Record<string, unknown>>(method: string) => {
    methods.push(method);
    if (method === 'sessions.create') throw new Error('Lost creation response');
    return { sessions: [existing] } as unknown as T;
  });
  assert.equal((await api.createSession(existing.key, settings)).key, existing.key);
  assert.deepEqual(methods, ['sessions.create', 'sessions.list']);
  assert.equal(useAppStore.getState().activeSessionKey, 'agents-session');
  await assert.rejects(api.createSession(existing.key, { ...settings, model: 'different-model' }), /different session settings/);
});
