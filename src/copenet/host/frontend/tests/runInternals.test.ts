import assert from 'node:assert/strict';
import test from 'node:test';

import { buildRunInternals, formatTokens, isBlockedStep, isFailedStep } from '../src/runtime/runInternals';
import type { ObservabilityTraceEvent, RunStep, SessionRunRecord } from '../src/types/backend';

function makeRun(overrides: Partial<SessionRunRecord> = {}): SessionRunRecord {
  return {
    runId: 'run-1',
    sessionKey: 'session-1',
    provider: 'openai-codex',
    model: 'gpt-5.5',
    status: 'ok',
    userMessage: 'Search the repo',
    toolExecutionMode: 'responses',
    willAttemptToolLoop: true,
    startedAt: '2026-08-02T03:00:00.000Z',
    completedAt: '2026-08-02T03:00:06.600Z',
    workingSet: {},
    toolSteps: [],
    artifactIds: [],
    outputSummary: 'Done.',
    error: null,
    metadata: {},
    terminalReason: 'completed',
    ...overrides,
  };
}

function traceEvent(event: string, payload: Record<string, unknown>): ObservabilityTraceEvent {
  return {
    timestamp: '2026-08-02T03:00:00.000Z',
    event,
    tier: 'lifecycle',
    runId: 'run-1',
    sessionKey: 'session-1',
    provider: 'openai-codex',
    model: 'gpt-5.5',
    payload,
  };
}

const okStep: RunStep = { toolId: 'files.rg', ok: true, summary: 'Found 3 matches.', arguments: { pattern: 'TODO' } };
const blockedStep: RunStep = {
  toolId: 'shell.exec',
  ok: false,
  summary: 'Tool blocked: shell.exec',
  policyDecision: 'write_blocked',
  policySummary: 'Current tool mode does not allow repository write tools.',
  arguments: { command: 'echo hi' },
};
const failedStep: RunStep = { toolId: 'web.fetch', ok: false, summary: 'Tool failed', error: 'connection refused' };

test('a blocked step and a failed step are different states', () => {
  assert.equal(isBlockedStep(blockedStep), true);
  assert.equal(isFailedStep(blockedStep), false);
  assert.equal(isFailedStep(failedStep), true);
  assert.equal(isBlockedStep(failedStep), false);
  assert.equal(isBlockedStep(okStep), false);
  assert.equal(isFailedStep(okStep), false);
});

test('token counts read for scale, not precision', () => {
  assert.equal(formatTokens(707), '707');
  assert.equal(formatTokens(1_500), '1.5k');
  assert.equal(formatTokens(12_400), '12k');
});

test('the collapsed line carries model, duration, tools, and context', () => {
  const internals = buildRunInternals(makeRun({ toolSteps: [okStep] }), [
    traceEvent('chat_messages_built', { messageCount: 13, inputTokenEstimate: 707, omittedMessageItemCount: 0 }),
  ]);

  assert.equal(internals.stat.model, 'gpt-5.5');
  assert.equal(internals.stat.durationLabel, '6.6s');
  assert.equal(internals.stat.toolCount, 1);
  assert.equal(internals.stat.contextLabel, '707 msg');
  assert.deepEqual(internals.stat.badges, []);
  assert.equal(internals.stat.tone, 'neutral');
});

test('badges surface blocks, failures, and trimming without expanding', () => {
  const internals = buildRunInternals(makeRun({ toolSteps: [blockedStep, failedStep] }), [
    traceEvent('chat_messages_built', { messageCount: 40, inputTokenEstimate: 98_000, omittedMessageItemCount: 6 }),
  ]);

  assert.deepEqual(
    internals.stat.badges.map((badge) => badge.label),
    ['1 blocked', '1 failed', 'trimmed'],
  );
  assert.equal(internals.stat.tone, 'error');
});

test('the no-tool-loop verdict names promptedToolUse, the usual culprit', () => {
  const internals = buildRunInternals(makeRun({ willAttemptToolLoop: false }), [
    traceEvent('harness_planned', {
      capabilityProfile: { promptedToolUse: false },
      willAttemptToolLoop: false,
      availableToolIds: ['files.read'],
    }),
  ]);

  const verdict = internals.verdicts.find((item) => item.id === 'no-tool-loop');
  assert.ok(verdict, 'expected a no-tool-loop verdict');
  assert.match(verdict.text, /promptedToolUse = false/);
  assert.equal(verdict.tone, 'warn');
});

test('a blocked call explains itself with the policy summary', () => {
  const internals = buildRunInternals(makeRun({ toolSteps: [blockedStep] }));
  const verdict = internals.verdicts.find((item) => item.id === 'blocked');
  assert.ok(verdict);
  assert.match(verdict.text, /1 tool call blocked/);
  assert.match(verdict.text, /does not allow repository write tools/);
});

test('"what it saw" reads the prompt and context-window trace rows', () => {
  const internals = buildRunInternals(makeRun(), [
    traceEvent('prompt_context_policy_resolved', {
      systemPromptId: null,
      baseSystemPromptChars: 11_527,
      rejectedRequestedToolIds: ['files.write'],
    }),
    traceEvent('prompt_context_assembled', {
      baseSystemPromptChars: 11_527,
      personaChars: 4_661,
      personaSpliced: true,
      contextOverlayChars: 0,
      toolCount: 16,
      toolSchemaChars: 21_487,
    }),
    traceEvent('chat_messages_built', {
      messageCount: 13,
      historyTurns: 6,
      inputTokenEstimate: 707,
      inputTokenBudget: 100_000,
      budgetSource: 'provider_fallback',
      omittedMessageItemCount: 0,
    }),
    traceEvent('harness_planned', { availableToolIds: ['files.read', 'files.rg'] }),
  ]);

  assert.equal(internals.saw.detailAvailable, true);
  const labels = internals.saw.promptBlocks.map((block) => block.label);
  assert.deepEqual(labels, ['System prompt', 'Persona', 'Tool schemas']);
  assert.equal(internals.saw.promptBlocks[0].value, '11.5k chars');
  assert.equal(internals.saw.promptBlocks[1].hint, 'spliced into the contract slot');

  const tokenRow = internals.saw.contextWindow.find((row) => row.label === 'Message tokens');
  assert.equal(tokenRow?.value, '707 / 100k');
  // The estimator charges the messages array only, so the label must not read as
  // "everything the model saw" — the prompt and schema sizes are their own rows.
  assert.match(tokenRow?.hint || '', /history only/);
  assert.deepEqual(internals.saw.offeredToolIds, ['files.read', 'files.rg']);
  assert.equal(internals.saw.withheldNote, 'Requested but withheld: files.write');
});

test('a run with no trace still produces a usable line and says why detail is missing', () => {
  const internals = buildRunInternals(makeRun({ toolSteps: [okStep] }));

  assert.equal(internals.hasTrace, false);
  assert.equal(internals.saw.detailAvailable, false);
  assert.equal(internals.stat.toolCount, 1);
  assert.equal(internals.did.length, 1);
  assert.equal(internals.stopped.text, 'The model finished its answer on its own.');
});

test('why it stopped distinguishes finishing from hitting the cap', () => {
  assert.match(
    buildRunInternals(makeRun({ terminalReason: 'max_turns' })).stopped.text,
    /tool-step cap/,
  );
  assert.equal(buildRunInternals(makeRun({ terminalReason: 'aborted' })).stopped.tone, 'warn');
  assert.equal(
    buildRunInternals(makeRun({ error: 'provider unavailable', status: 'error' })).stopped.tone,
    'error',
  );
});
