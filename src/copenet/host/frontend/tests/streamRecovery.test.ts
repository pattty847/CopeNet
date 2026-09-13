import assert from 'node:assert/strict';
import test from 'node:test';
import { useAppStore } from '../src/store/useAppStore';
import { loadHistoryAction } from '../src/lib/wsSessionActions';
import { handleChatEventAction } from '../src/lib/wsChatEvents';

let sessionKey = '';
let sessionCount = 0;
const refresh = async () => {};
const message = (content: string, state = 'delta') => ({ runId: 'run', role: 'assistant', content, state });
const delta = (seq: number, content: string) => handleChatEventAction({ sessionKey, runId: 'run', seq, state: 'delta', message: message(content) }, refresh, refresh);
function reset() {
  sessionKey = `recovery-${++sessionCount}`;
  useAppStore.setState({ messages: {}, pendingAssistants: {}, activeRunsBySession: {} });
}

test('reopened browser recovers the full active answer and continues appending', async () => {
  reset();
  await loadHistoryAction(async () => ({ messages: [], activeRun: { runId: 'run', seq: 3, message: message('Before close. While away.') } }) as any, sessionKey);
  delta(4, ' After return.');
  const messages = useAppStore.getState().messages[sessionKey];
  assert.equal(messages.length, 1);
  assert.equal(messages[0].content, 'Before close. While away. After return.');
  assert.equal(useAppStore.getState().activeRunsBySession[sessionKey], 'run');
});

test('history races neither duplicate snapshot deltas nor lose newer ones', async () => {
  reset();
  let resolve!: (value: any) => void;
  const loading = loadHistoryAction(() => new Promise((done) => { resolve = done; }), sessionKey);
  delta(2, 'already in snapshot');
  delta(3, ' newer');
  resolve({ messages: [], activeRun: { runId: 'run', seq: 2, message: message('complete snapshot') } });
  await loading;
  assert.equal(useAppStore.getState().messages[sessionKey][0].content, 'complete snapshot newer');
});

test('completion while away replaces pending output without a duplicate answer', async () => {
  reset();
  delta(1, 'partial');
  const localId = useAppStore.getState().messages[sessionKey][0].localId;
  let resolve!: (value: any) => void;
  const loading = loadHistoryAction(() => new Promise((done) => { resolve = done; }), sessionKey);
  delta(2, 'stale queued delta');
  resolve({ messages: [message('finished answer', 'final')], activeRun: null });
  await loading;
  assert.equal(useAppStore.getState().messages[sessionKey].length, 1);
  assert.equal(useAppStore.getState().messages[sessionKey][0].content, 'finished answer');
  assert.equal(useAppStore.getState().messages[sessionKey][0].localId, localId);
  assert.equal(useAppStore.getState().pendingAssistants.run, undefined);
});

test('failed recovery releases live events and allows a subsequent retry', async () => {
  reset();
  let reject!: (error: Error) => void;
  const loading = loadHistoryAction(() => new Promise((_, fail) => { reject = fail; }), sessionKey);
  delta(1, 'still live');
  reject(new Error('offline'));
  await assert.rejects(loading, /offline/);
  assert.equal(useAppStore.getState().messages[sessionKey][0].content, 'still live');
});


test('late delivery of an event covered by the snapshot is ignored', async () => {
  reset();
  await loadHistoryAction(async () => ({ messages: [], activeRun: { runId: 'run', seq: 2, message: message('snapshot') } }) as any, sessionKey);
  delta(2, 'old chunk');
  delta(3, ' new chunk');
  assert.equal(useAppStore.getState().messages[sessionKey][0].content, 'snapshot new chunk');
});
