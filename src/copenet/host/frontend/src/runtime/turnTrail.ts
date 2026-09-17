/**
 * turnTrail — how one assistant turn's parts are laid out in the thread.
 *
 * Two rules, both about time:
 *
 *   1. Parts render in the order they happened. Consecutive tool parts form a
 *      group; narration or reasoning closes it, and the next call opens a new one.
 *      A group never reaches backwards to absorb a call made after some text.
 *   2. The ANSWER is the text after the last action. While the run is live the
 *      whole turn is shown in order so it can be followed; once it settles,
 *      everything before the answer folds into one collapsed trail box, and
 *      opening that box shows the same ordered trail.
 *
 * Pure: no React, no store. `components/transcript/TurnTrail.tsx` renders it.
 */

import type { MessagePart, TextPart, ThinkingPart, ToolBatchPart, ToolCallPart, ToolResultPart } from '../types/backend';

export type ToolPart = ToolCallPart | ToolResultPart | ToolBatchPart;

export type TrailSegment =
  | { kind: 'text'; part: TextPart }
  | { kind: 'thinking'; part: ThinkingPart }
  | { kind: 'tools'; parts: ToolPart[] };

export function isToolPart(part: MessagePart): part is ToolPart {
  return part.kind === 'tool_call' || part.kind === 'tool_result' || part.kind === 'tool_batch';
}

function callIsAnsweredBy(call: ToolCallPart, next: MessagePart | undefined): boolean {
  if (!next) return false;
  if (next.kind === 'tool_result') {
    if (call.callId && next.callId && call.callId === next.callId) return true;
    return call.toolId === next.toolId;
  }
  if (next.kind === 'tool_batch') return call.toolId === 'tool.batch';
  return false;
}

/** A call row exists only until its result arrives; the result row replaces it. */
export function collapseRenderedMessageParts(parts: MessagePart[]): MessagePart[] {
  return parts.filter((part, index) => !(part.kind === 'tool_call' && callIsAnsweredBy(part, parts[index + 1])));
}

/** Ordered segments: runs of consecutive tool parts become one `tools` segment. */
export function segmentTrail(parts: MessagePart[]): TrailSegment[] {
  const segments: TrailSegment[] = [];
  for (const part of parts) {
    if (isToolPart(part)) {
      const last = segments[segments.length - 1];
      if (last?.kind === 'tools') last.parts.push(part);
      else segments.push({ kind: 'tools', parts: [part] });
    } else if (part.kind === 'text') {
      if (part.content) segments.push({ kind: 'text', part });
    } else {
      segments.push({ kind: 'thinking', part });
    }
  }
  return segments;
}

/** Split a settled turn into the trail (everything up to and including the last
 *  non-text part) and the answer (the text after it). A turn with no actions and
 *  no reasoning is all answer. */
export function splitTurn(parts: MessagePart[]): { trail: MessagePart[]; answer: TextPart[] } {
  let lastNonText = -1;
  parts.forEach((part, index) => {
    if (part.kind !== 'text') lastNonText = index;
  });
  return {
    trail: parts.slice(0, lastNonText + 1),
    answer: parts.slice(lastNonText + 1).filter((part): part is TextPart => part.kind === 'text'),
  };
}

// ---------------------------------------------------------------------------
// Titles — what a row and a group header say. Derived from the tool id and its
// target; a model-supplied title is future work and would slot in ahead of this.
// ---------------------------------------------------------------------------

interface ToolPhrase {
  /** Row label, past tense: "Ran shell command". */
  done: string;
  /** Row label while in flight: "Running shell command". */
  doing: string;
  /** Header phrase for n > 1 calls, lower case: "ran 3 commands". */
  many: (count: number) => string;
  /** How the target reads: a path is shortened, a command/query is shown as typed. */
  target: 'path' | 'literal' | 'host' | 'none';
  /** Whether a single call names its target in a group header ("read model_tables.py"). */
  namesTargetInHeader?: boolean;
}

const TOOL_PHRASES: Record<string, ToolPhrase> = {
  'shell.exec': { done: 'Ran shell command', doing: 'Running shell command', many: (n) => `ran ${n} commands`, target: 'literal' },
  'files.read': { done: 'Read', doing: 'Reading', many: (n) => `read ${n} files`, target: 'path', namesTargetInHeader: true },
  'files.rg': { done: 'Searched for', doing: 'Searching for', many: (n) => `ran ${n} searches`, target: 'literal' },
  'files.edit': { done: 'Edited', doing: 'Editing', many: (n) => `made ${n} edits`, target: 'path', namesTargetInHeader: true },
  'files.write': { done: 'Wrote', doing: 'Writing', many: (n) => `wrote ${n} files`, target: 'path', namesTargetInHeader: true },
  'plan.write': { done: 'Updated the plan', doing: 'Updating the plan', many: (n) => `updated the plan ${n} times`, target: 'none' },
  'web.search': { done: 'Searched the web for', doing: 'Searching the web for', many: (n) => `ran ${n} web searches`, target: 'literal' },
  'web.fetch': { done: 'Fetched', doing: 'Fetching', many: (n) => `fetched ${n} pages`, target: 'host', namesTargetInHeader: true },
  'artifact.read': { done: 'Opened artifact', doing: 'Opening artifact', many: (n) => `opened ${n} artifacts`, target: 'literal' },
  'memory.read': { done: 'Read memory', doing: 'Reading memory', many: (n) => `read memory ${n} times`, target: 'none' },
  'tools.load': { done: 'Loaded tools', doing: 'Loading tools', many: (n) => `loaded tools ${n} times`, target: 'none' },
};

const SINGLE_HEADER: Record<string, string> = {
  'shell.exec': 'ran a command',
  'files.rg': 'ran a search',
  'web.search': 'searched the web',
};

function phraseFor(toolId: string): ToolPhrase {
  return TOOL_PHRASES[toolId] || {
    done: `Used ${toolId}`,
    doing: `Using ${toolId}`,
    many: (n) => `used ${toolId} ${n} times`,
    target: 'literal',
  };
}

export function fileName(path: string): string {
  const segments = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return segments[segments.length - 1] || path;
}

/** Last two path segments: "…/components/MessageBubble.tsx". */
export function shortPath(path: string): string {
  const segments = path.replace(/\\/g, '/').split('/').filter(Boolean);
  if (segments.length <= 2) return path;
  return `…/${segments.slice(-2).join('/')}`;
}

function hostOf(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return url;
  }
}

export interface ToolRowTitle {
  label: string;
  /** The target as it should be displayed, or null when the label says it all. */
  detail: string | null;
  /** True when the detail is something typed (a command, a pattern) — render mono. */
  literal: boolean;
}

export function toolRowTitle(
  toolId: string,
  target: string | null | undefined,
  options: { inFlight?: boolean; summary?: string | null } = {},
): ToolRowTitle {
  // A tool with no phrase yet says what its own result summary says, which beats
  // a raw id. Phrases are added per tool as each one is reviewed.
  if (!TOOL_PHRASES[toolId] && options.summary) return { label: options.summary, detail: null, literal: false };
  const phrase = phraseFor(toolId);
  const label = options.inFlight ? phrase.doing : phrase.done;
  const raw = (target || '').trim();
  if (!raw || phrase.target === 'none') return { label, detail: null, literal: false };
  if (phrase.target === 'path') return { label, detail: shortPath(raw), literal: false };
  if (phrase.target === 'host') return { label, detail: hostOf(raw), literal: false };
  return { label: `${label}:`, detail: raw, literal: true };
}

interface HeaderBucket {
  toolId: string;
  count: number;
  firstTarget: string | null;
}

/** Group header: "Ran 2 commands, read model_tables.py". One phrase per tool in
 *  the order it first appeared, so the header reads like the work did. */
export function summarizeToolParts(parts: MessagePart[]): string {
  const buckets = new Map<string, HeaderBucket>();
  const add = (toolId: string, target: string | null | undefined) => {
    const bucket = buckets.get(toolId);
    if (bucket) bucket.count += 1;
    else buckets.set(toolId, { toolId, count: 1, firstTarget: target || null });
  };
  for (const part of parts) {
    if (part.kind === 'tool_batch') part.members.forEach((member) => add(member.toolId, member.target));
    else if (part.kind === 'tool_call' || part.kind === 'tool_result') add(part.toolId, part.target);
  }
  if (buckets.size === 0) return 'No tools used';

  const phrases = [...buckets.values()].map((bucket) => {
    const phrase = phraseFor(bucket.toolId);
    if (bucket.count > 1) return phrase.many(bucket.count);
    if (phrase.namesTargetInHeader && bucket.firstTarget) {
      const shown = phrase.target === 'host' ? hostOf(bucket.firstTarget) : fileName(bucket.firstTarget);
      return `${phrase.done.toLowerCase()} ${shown}`;
    }
    return SINGLE_HEADER[bucket.toolId] || phrase.done.toLowerCase();
  });
  const joined = phrases.join(', ');
  return joined.charAt(0).toUpperCase() + joined.slice(1);
}

export function countFailedToolParts(parts: MessagePart[]): number {
  let failed = 0;
  for (const part of parts) {
    if (part.kind === 'tool_result' && !part.ok) failed += 1;
    if (part.kind === 'tool_batch') failed += part.members.filter((member) => !member.ok).length;
  }
  return failed;
}
