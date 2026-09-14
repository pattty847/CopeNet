import assert from 'node:assert/strict';
import test from 'node:test';

import { buildRunInternals, formatTokens, isBlockedStep, isFailedStep, tokenReadout } from '../src/runtime/runInternals';
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
  assert.equal(internals.stat.contextLabel, '~707 msg');
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

test('provider-reported usage replaces the estimate in the stat line and the saw section', () => {
  const run = makeRun({
    inputTokenEstimate: 17_801,
    tokenUsage: {
      source: 'provider', modelCalls: 3, inputTokens: 125_631, peakInputTokens: 52_079,
      cachedInputTokens: 65_000, outputTokens: 2_530, reasoningTokens: 712, steps: [],
    },
  });
  const internals = buildRunInternals(run, [traceEvent('chat_messages_built', { inputTokenEstimate: 17_801, inputTokenBudget: 120_000 })]);

  assert.equal(internals.stat.contextLabel, '52k ctx · 2.5k out');
  const labels = internals.saw.contextWindow.map((fact) => fact.label);
  assert.deepEqual(labels.slice(0, 3), ['Context size', 'Input billed', 'Output tokens']);
  assert.equal(internals.saw.contextWindow[1].value, '126k');
  assert.match(internals.saw.contextWindow[1].hint ?? '', /65k served from cache/);
  assert.ok(labels.includes('Message tokens'), 'the tokenizer estimate stays, labelled as such');
});

test('without provider usage the readout is the estimate, marked as one', () => {
  assert.equal(tokenReadout(makeRun({ inputTokenEstimate: 17_801 })), '~18k msg');
  assert.equal(tokenReadout(makeRun({ tokenUsage: null })), null);
  assert.equal(tokenReadout(makeRun({ tokenUsage: { source: 'provider', modelCalls: 1, inputTokens: 900, peakInputTokens: 900, cachedInputTokens: null, outputTokens: null, reasoningTokens: null, steps: [] } })), '900 ctx');
});

test('coding metrics become a "How it worked" section and verdicts for the costly habits', () => {
  const run = makeRun({
    codingMetrics: {
      toolCalls: 9,
      reads: { distinctFiles: 4, redundant: 2, afterOwnEdit: 1 },
      searches: { count: 3, overCap: 1, cap: 200 },
      edits: { count: 2, files: 1, staleErrors: 0 },
      exactRepeats: 0,
      failures: { count: 1, blocked: 0, blindRetries: 1 },
      verification: { commands: 0, tests: 0, afterLastEdit: false },
      recovery: { failedVerificationsAfterEdit: 0, editsAfterFailedVerification: 0 },
    },
  });
  const internals = buildRunInternals(run, []);
  const labels = internals.worked.map((fact) => fact.label);
  assert.deepEqual(labels, ['Reads', 'Searches', 'Edits', 'Verification', 'Waste']);
  assert.equal(internals.worked[0].value, '4 files');
  assert.match(internals.worked[0].hint ?? '', /2 redundant · 1 re-read after own edit/);
  assert.equal(internals.worked[3].value, 'none');
  assert.equal(internals.worked[3].hint, 'nothing ran after the last edit');
  const ids = internals.verdicts.map((verdict) => verdict.id);
  assert.deepEqual(ids, ['unverified-edit', 'blind-retry', 'search-dump', 'redundant-read']);
});

test('a chat-only turn has no coding section and no coding verdicts', () => {
  const internals = buildRunInternals(makeRun({ codingMetrics: null }), []);
  assert.deepEqual(internals.worked, []);
  assert.equal(internals.verdicts.some((verdict) => verdict.id === 'unverified-edit'), false);
});
