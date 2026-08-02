/**
 * runInternals — the one derivation of "what happened inside this turn".
 *
 * Four surfaces used to answer this question in four different shapes
 * (LiveToolFeed, RunActivityPanel, ToolTraceCard, RunInspector). This module is
 * the single model they can all render: it takes a durable `SessionRunRecord`
 * and, when available, that run's lifecycle trace, and produces the collapsed
 * stat line plus the four sections a person actually debugs in order — what it
 * saw, what it did, why it stopped, raw trace.
 *
 * Deliberately pure and React-free so the interesting logic (verdicts, tone,
 * withheld-tool reasoning) is testable without mounting anything.
 *
 * The run record alone is enough for the stat line, the tool steps, and the
 * terminal reason. The trace adds the prompt/context/manifest detail, which is
 * why `events` is optional rather than required.
 */

import type { ObservabilityTraceEvent, RunStep, SessionRunRecord } from '../types/backend';

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
  const tokens = num(built?.inputTokenEstimate) ?? num(run.inputTokenEstimate);

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
    contextLabel: tokens != null ? `${formatTokens(tokens)} msg` : null,
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

  if (run.error) {
    verdicts.push({ id: 'run-error', text: run.error, tone: 'error' });
  }

  return verdicts;
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
      hint: 'history only — prompt and schemas are above',
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
    stopped: buildStopped(run, events),
    events,
    hasTrace: events.length > 0,
  };
}
