/**
 * runInternals — the one derivation of "what happened inside this turn".
 *
 * Four surfaces used to answer this question in four different shapes
 * (LiveToolFeed, RunActivityPanel, ToolTraceCard, RunInspector). This module is
 * the single model they can all render: it takes a durable `SessionRunRecord`
 * and, when available, that run's lifecycle trace, and produces the collapsed
 * stat line plus the sections a person actually debugs in order — what it
 * saw, what it did, how it worked, why it stopped, raw trace.
 *
 * Deliberately pure and React-free so the interesting logic (verdicts, tone,
 * withheld-tool reasoning) is testable without mounting anything.
 *
 * The run record alone is enough for the stat line, the tool steps, and the
 * terminal reason. The trace adds the prompt/context/manifest detail, which is
 * why `events` is optional rather than required.
 */

import type { ObservabilityTraceEvent, RunCodingMetrics, RunStep, RunTokenUsage, SessionRunRecord } from '../types/backend';

export type InternalsTone = 'neutral' | 'warn' | 'error';

export interface InternalsBadge {
  label: string;
  tone: InternalsTone;
}

export interface InternalsStat {
  model: string;
  durationLabel: string;
  toolCount: number;
  contextLabel: string | null;
  badges: InternalsBadge[];
  tone: InternalsTone;
}

export interface InternalsVerdict {
  id: string;
  text: string;
  tone: InternalsTone;
}

export interface InternalsFact {
  label: string;
  value: string;
  hint?: string | null;
}

export interface InternalsSaw {
  promptBlocks: InternalsFact[];
  contextWindow: InternalsFact[];
  offeredToolIds: string[];
  withheldNote: string | null;
  detailAvailable: boolean;
}

export interface RunInternals {
  runId: string;
  sessionKey: string;
  stat: InternalsStat;
  verdicts: InternalsVerdict[];
  saw: InternalsSaw;
  did: RunStep[];
  /** Coding-behavior facts from the run record's codingMetrics; empty for chat-only turns. */
  worked: InternalsFact[];
  stopped: { text: string; tone: InternalsTone };
  events: ObservabilityTraceEvent[];
  hasTrace: boolean;
}

const BLOCKED_DECISIONS = new Set(['write_blocked', 'unsafe_unknown', 'approval_required']);

function payloadOf(events: ObservabilityTraceEvent[], name: string): Record<string, unknown> | null {
  const hit = events.find((event) => event.event === name);
  return hit && hit.payload && typeof hit.payload === 'object' ? hit.payload : null;
}

function num(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function isBlockedStep(step: RunStep): boolean {
  if (step.policyDecision && BLOCKED_DECISIONS.has(step.policyDecision)) return true;
  return step.ok === false && !step.error;
}

export function isFailedStep(step: RunStep): boolean {
  return step.ok === false && !isBlockedStep(step);
}

/** "12k" past a thousand, exact below it — a token count is only ever read for scale. */
export function formatTokens(tokens: number): string {
  if (tokens < 1_000) return String(tokens);
  return `${(tokens / 1_000).toFixed(tokens < 10_000 ? 1 : 0).replace(/\.0$/, '')}k`;
}

/** The one-line token readout for a turn: provider-reported when the provider
 *  reported it, otherwise the tokenizer estimate of the message history, and
 *  labelled so nobody mistakes one for the other. */
export function tokenReadout(run: Pick<SessionRunRecord, 'tokenUsage' | 'inputTokenEstimate'>, estimate?: number | null): string | null {
  const usage = run.tokenUsage;
  if (usage && (usage.peakInputTokens != null || usage.outputTokens != null)) {
    const parts: string[] = [];
    if (usage.peakInputTokens != null) parts.push(`${formatTokens(usage.peakInputTokens)} ctx`);
    if (usage.outputTokens != null) parts.push(`${formatTokens(usage.outputTokens)} out`);
    return parts.join(' · ');
  }
  const fallback = num(estimate) ?? num(run.inputTokenEstimate);
  return fallback != null ? `~${formatTokens(fallback)} msg` : null;
}

export function formatChars(chars: number): string {
  if (chars < 1_000) return `${chars} chars`;
  return `${(chars / 1_000).toFixed(1).replace(/\.0$/, '')}k chars`;
}

function durationLabel(startedAt: string, completedAt: string | null): string {
  const start = new Date(startedAt).getTime();
  const end = completedAt ? new Date(completedAt).getTime() : NaN;
  if (Number.isNaN(start) || Number.isNaN(end)) return '—';
  const ms = Math.max(0, end - start);
  if (ms < 1_000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1_000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60_000);
  return `${mins}m${Math.round((ms % 60_000) / 1_000)}s`;
}

function buildStat(run: SessionRunRecord, events: ObservabilityTraceEvent[]): InternalsStat {
  const blocked = run.toolSteps.filter(isBlockedStep).length;
  const failed = run.toolSteps.filter(isFailedStep).length;
  const built = payloadOf(events, 'chat_messages_built');
  const omitted = num(built?.omittedMessageItemCount) ?? 0;

  const badges: InternalsBadge[] = [];
  if (blocked > 0) badges.push({ label: `${blocked} blocked`, tone: 'warn' });
  if (failed > 0) badges.push({ label: `${failed} failed`, tone: 'error' });
  if (omitted > 0) badges.push({ label: 'trimmed', tone: 'warn' });
  if (run.error) badges.push({ label: 'run failed', tone: 'error' });

  const tone: InternalsTone = badges.some((badge) => badge.tone === 'error')
    ? 'error'
    : badges.length > 0
      ? 'warn'
      : 'neutral';

  return {
    model: run.model || run.provider || 'unknown model',
    durationLabel: durationLabel(run.startedAt, run.completedAt),
    toolCount: run.toolSteps.length,
    contextLabel: tokenReadout(run, num(built?.inputTokenEstimate)),
    badges,
    tone,
  };
}

/**
 * Verdicts answer the question before the operator has to read anything.
 * Ordered by how often each one is the actual explanation, per this repo's own
 * triage order — "the tool loop never ran" is first because it is the single
 * most common source of "why didn't it use the tool?"
 */
function buildVerdicts(run: SessionRunRecord, events: ObservabilityTraceEvent[]): InternalsVerdict[] {
  const verdicts: InternalsVerdict[] = [];
  const planned = payloadOf(events, 'harness_planned');
  const profile = planned?.capabilityProfile && typeof planned.capabilityProfile === 'object'
    ? planned.capabilityProfile as Record<string, unknown>
    : null;
  const offered = Array.isArray(planned?.availableToolIds) ? planned.availableToolIds.length : null;

  if (run.willAttemptToolLoop === false) {
    const reason = profile?.promptedToolUse === false
      ? 'promptedToolUse = false for this provider/model'
      : offered === 0
        ? 'no tools were offered at this Access level'
        : 'the harness planned a chat-only turn';
    verdicts.push({ id: 'no-tool-loop', text: `No tool loop attempted — ${reason}.`, tone: 'warn' });
  }

  const blocked = run.toolSteps.filter(isBlockedStep);
  if (blocked.length > 0) {
    const summary = blocked[0].policySummary || blocked[0].summary || 'blocked by policy';
    verdicts.push({
      id: 'blocked',
      text: `${blocked.length} tool call${blocked.length === 1 ? '' : 's'} blocked — ${summary}`,
      tone: 'warn',
    });
  }

  const failed = run.toolSteps.filter(isFailedStep);
  if (failed.length > 0) {
    verdicts.push({
      id: 'tool-failed',
      text: `${failed.length} tool call${failed.length === 1 ? '' : 's'} failed — ${failed[0].error || 'no error detail'}`,
      tone: 'error',
    });
  }

  const built = payloadOf(events, 'chat_messages_built');
  const omitted = num(built?.omittedMessageItemCount) ?? 0;
  if (omitted > 0) {
    verdicts.push({
      id: 'trimmed',
      text: `Context trimmed — ${omitted} message item${omitted === 1 ? '' : 's'} dropped to fit the input budget.`,
      tone: 'warn',
    });
  }

  if (run.terminalReason === 'max_turns') {
    verdicts.push({ id: 'max-turns', text: 'Stopped at the tool-step cap, not because it finished.', tone: 'warn' });
  }

  verdicts.push(...codingVerdicts(run.codingMetrics ?? null));

  if (run.error) {
    verdicts.push({ id: 'run-error', text: run.error, tone: 'error' });
  }

  return verdicts;
}

/** The coding-behavior verdicts: each one is a habit the harness audit found
 *  costing real turns, so each is worth a line before the operator reads anything. */
function codingVerdicts(metrics: RunCodingMetrics | null): InternalsVerdict[] {
  if (!metrics) return [];
  const verdicts: InternalsVerdict[] = [];
  if (metrics.verification.afterLastEdit === false) {
    const files = metrics.edits.files === 1 ? '1 file' : `${metrics.edits.files} files`;
    verdicts.push({ id: 'unverified-edit', text: `Edited ${files} and ran no test, lint or build afterwards.`, tone: 'warn' });
  }
  if (metrics.edits.staleErrors > 0) {
    verdicts.push({ id: 'stale-edit', text: `${metrics.edits.staleErrors} edit${metrics.edits.staleErrors === 1 ? '' : 's'} refused as stale — the file changed since it was last read.`, tone: 'warn' });
  }
  if (metrics.failures.blindRetries > 0) {
    verdicts.push({ id: 'blind-retry', text: `${metrics.failures.blindRetries} failed call${metrics.failures.blindRetries === 1 ? '' : 's'} re-issued unchanged.`, tone: 'warn' });
  }
  if (metrics.searches.overCap > 0) {
    verdicts.push({ id: 'search-dump', text: `${metrics.searches.overCap} search${metrics.searches.overCap === 1 ? '' : 'es'} returned more than ${metrics.searches.cap} matches.`, tone: 'warn' });
  }
  if (metrics.reads.redundant > 0) {
    verdicts.push({ id: 'redundant-read', text: `${metrics.reads.redundant} redundant read${metrics.reads.redundant === 1 ? '' : 's'} — a range already in context, nothing edited between.`, tone: 'neutral' });
  }
  return verdicts;
}

function buildWorked(metrics: RunCodingMetrics | null): InternalsFact[] {
  if (!metrics) return [];
  const facts: InternalsFact[] = [];
  const reads = metrics.reads;
  facts.push({
    label: 'Reads',
    value: `${reads.distinctFiles} file${reads.distinctFiles === 1 ? '' : 's'}`,
    hint: [reads.redundant > 0 ? `${reads.redundant} redundant` : null, reads.afterOwnEdit > 0 ? `${reads.afterOwnEdit} re-read after own edit` : null]
      .filter(Boolean)
      .join(' · ') || 'no re-reads',
  });
  if (metrics.searches.count > 0) {
    facts.push({
      label: 'Searches',
      value: String(metrics.searches.count),
      hint: metrics.searches.overCap > 0 ? `${metrics.searches.overCap} over the ${metrics.searches.cap}-match cap` : `none over the ${metrics.searches.cap}-match cap`,
    });
  }
  if (metrics.edits.count > 0) {
    facts.push({
      label: 'Edits',
      value: `${metrics.edits.count} in ${metrics.edits.files} file${metrics.edits.files === 1 ? '' : 's'}`,
      hint: metrics.edits.staleErrors > 0 ? `${metrics.edits.staleErrors} refused as stale` : null,
    });
  }
  const verification = metrics.verification;
  facts.push({
    label: 'Verification',
    value: verification.commands === 0 ? 'none' : `${verification.commands} command${verification.commands === 1 ? '' : 's'}`,
    hint: verification.afterLastEdit === null
      ? (verification.commands > 0 ? `${verification.tests} test run${verification.tests === 1 ? '' : 's'}` : 'nothing was edited')
      : verification.afterLastEdit
        ? 'ran after the last edit'
        : 'nothing ran after the last edit',
  });
  if (metrics.recovery.failedVerificationsAfterEdit > 0) {
    facts.push({
      label: 'Recovery',
      value: `${metrics.recovery.editsAfterFailedVerification} edit${metrics.recovery.editsAfterFailedVerification === 1 ? '' : 's'} after a red run`,
      hint: `${metrics.recovery.failedVerificationsAfterEdit} verification${metrics.recovery.failedVerificationsAfterEdit === 1 ? '' : 's'} failed after an edit`,
    });
  }
  if (metrics.failures.count > 0 || metrics.exactRepeats > 0) {
    facts.push({
      label: 'Waste',
      value: [metrics.failures.count > 0 ? `${metrics.failures.count} failed` : null, metrics.exactRepeats > 0 ? `${metrics.exactRepeats} repeated` : null].filter(Boolean).join(' · '),
      hint: metrics.failures.blindRetries > 0 ? `${metrics.failures.blindRetries} blind retr${metrics.failures.blindRetries === 1 ? 'y' : 'ies'}` : null,
    });
  }
  return facts;
}

function buildSaw(run: SessionRunRecord, events: ObservabilityTraceEvent[]): InternalsSaw {
  const policy = payloadOf(events, 'prompt_context_policy_resolved');
  const assembled = payloadOf(events, 'prompt_context_assembled');
  const built = payloadOf(events, 'chat_messages_built');
  const planned = payloadOf(events, 'harness_planned');

  const promptBlocks: InternalsFact[] = [];
  const base = num(assembled?.baseSystemPromptChars) ?? num(policy?.baseSystemPromptChars);
  if (base != null) {
    promptBlocks.push({
      label: 'System prompt',
      value: formatChars(base),
      hint: typeof policy?.systemPromptId === 'string' ? policy.systemPromptId : 'composed default',
    });
  }
  const persona = num(assembled?.personaChars);
  if (persona != null && persona > 0) {
    promptBlocks.push({
      label: 'Persona',
      value: formatChars(persona),
      hint: assembled?.personaSpliced === true ? 'spliced into the contract slot' : 'appended',
    });
  }
  const overlay = num(assembled?.contextOverlayChars);
  if (overlay != null && overlay > 0) {
    promptBlocks.push({ label: 'Memory overlay', value: formatChars(overlay), hint: 'relevant memory' });
  }
  const schemas = num(assembled?.toolSchemaChars);
  if (schemas != null && schemas > 0) {
    const count = num(assembled?.toolCount);
    promptBlocks.push({
      label: 'Tool schemas',
      value: formatChars(schemas),
      hint: count != null ? `${count} tools` : null,
    });
  }

  const contextWindow: InternalsFact[] = [];
  const messages = num(built?.messageCount);
  if (messages != null) {
    const turns = num(built?.historyTurns);
    contextWindow.push({
      label: 'Messages sent',
      value: String(messages),
      hint: turns != null ? `${turns} prior turns replayed` : null,
    });
  }
  // Provider-reported usage first: it is the only number that is not ours.
  // Every tool step re-sends the whole context, so the billed input is a sum and
  // the peak is the context size — both are shown because they answer different
  // questions ("what did this cost" vs "how big was the packet").
  const usage = run.tokenUsage;
  if (usage) {
    contextWindow.push(...usageFacts(usage));
  }
  // Named "message tokens", not "input tokens": the estimator charges the
  // messages array only. A turn can read as "5 tokens" while the model was
  // actually handed a 16k-char system prompt and 21k of tool schemas, which is
  // exactly the kind of number that makes a debugging session go sideways.
  const estimate = num(built?.inputTokenEstimate);
  const budget = num(built?.inputTokenBudget);
  if (estimate != null) {
    contextWindow.push({
      label: 'Message tokens',
      value: budget != null ? `${formatTokens(estimate)} / ${formatTokens(budget)}` : formatTokens(estimate),
      hint: 'tokenizer count of history only — prompt and schemas are above',
    });
  }
  if (budget != null && typeof built?.budgetSource === 'string') {
    contextWindow.push({ label: 'Budget source', value: built.budgetSource, hint: null });
  }
  const omitted = num(built?.omittedMessageItemCount) ?? 0;
  if (omitted > 0) {
    contextWindow.push({ label: 'Trimmed', value: `${omitted} items dropped`, hint: 'over the input budget' });
  }
  if (built?.cliResume === true) {
    contextWindow.push({
      label: 'CLI resume',
      value: 'on',
      hint: 'only the new message was sent; the provider holds the thread',
    });
  }

  const offeredToolIds = Array.isArray(planned?.availableToolIds)
    ? planned.availableToolIds.filter((id): id is string => typeof id === 'string')
    : [];

  // The trace records rejections explicitly, so say which ids were dropped
  // rather than leaving the operator to diff two lists by eye.
  const rejected = Array.isArray(policy?.rejectedRequestedToolIds)
    ? policy.rejectedRequestedToolIds.filter((id): id is string => typeof id === 'string')
    : [];
  const withheldNote = rejected.length > 0
    ? `Requested but withheld: ${rejected.join(', ')}`
    : offeredToolIds.length === 0 && events.length > 0
      ? 'No tools were offered for this turn.'
      : null;

  return {
    promptBlocks,
    contextWindow,
    offeredToolIds,
    withheldNote,
    detailAvailable: promptBlocks.length > 0 || contextWindow.length > 0 || offeredToolIds.length > 0,
  };
}

function usageFacts(usage: RunTokenUsage): InternalsFact[] {
  const facts: InternalsFact[] = [];
  const calls = usage.modelCalls === 1 ? '1 model call' : `${usage.modelCalls} model calls`;
  if (usage.peakInputTokens != null) {
    facts.push({ label: 'Context size', value: formatTokens(usage.peakInputTokens), hint: `largest input the provider reported · ${calls}` });
  }
  if (usage.inputTokens != null) {
    const cached = usage.cachedInputTokens != null && usage.cachedInputTokens > 0
      ? `${formatTokens(usage.cachedInputTokens)} served from cache`
      : 'summed over every model call';
    facts.push({ label: 'Input billed', value: formatTokens(usage.inputTokens), hint: cached });
  }
  if (usage.outputTokens != null) {
    const reasoning = usage.reasoningTokens != null && usage.reasoningTokens > 0
      ? `${formatTokens(usage.reasoningTokens)} of it reasoning`
      : 'reported by the provider';
    facts.push({ label: 'Output tokens', value: formatTokens(usage.outputTokens), hint: reasoning });
  }
  return facts;
}

function buildStopped(run: SessionRunRecord, events: ObservabilityTraceEvent[]): { text: string; tone: InternalsTone } {
  if (run.error) return { text: `Run failed: ${run.error}`, tone: 'error' };

  const reason = run.terminalReason
    || (payloadOf(events, 'turn_completed')?.terminalReason as string | undefined)
    || null;

  switch (reason) {
    case 'completed':
      return { text: 'The model finished its answer on its own.', tone: 'neutral' };
    case 'max_turns':
      return { text: 'Hit the tool-step cap before the model chose to stop.', tone: 'warn' };
    case 'aborted':
      return { text: 'Stopped early — the run was aborted.', tone: 'warn' };
    default:
      break;
  }
  if (run.status === 'ok') return { text: 'The model finished its answer on its own.', tone: 'neutral' };
  return { text: `Terminal state: ${run.status}.`, tone: run.status === 'error' ? 'error' : 'neutral' };
}

export function buildRunInternals(
  run: SessionRunRecord,
  events: ObservabilityTraceEvent[] = [],
): RunInternals {
  return {
    runId: run.runId,
    sessionKey: run.sessionKey,
    stat: buildStat(run, events),
    verdicts: buildVerdicts(run, events),
    saw: buildSaw(run, events),
    did: run.toolSteps,
    worked: buildWorked(run.codingMetrics ?? null),
    stopped: buildStopped(run, events),
    events,
    hasTrace: events.length > 0,
  };
}
