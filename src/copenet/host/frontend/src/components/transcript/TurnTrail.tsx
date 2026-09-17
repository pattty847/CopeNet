/**
 * TurnTrail — one assistant turn in the thread: what it did, then what it said.
 *
 * While the run is live, the turn renders in the order it happened — narration,
 * reasoning, and collapsed groups of consecutive tool calls — so it can be
 * followed as it goes. A group is collapsed from the start and stays that way:
 * most readers are not following tool calls, and a box that opens itself and
 * grows pushes the text they are reading down the screen.
 *
 * Once the turn settles, everything before the answer folds into ONE collapsed
 * trail box above it. Opening the box shows the same ordered trail, so the
 * record of "when did it do that" survives; only the default changes, from
 * "watch it work" to "read the answer".
 *
 * The layout rules are pure and live in `runtime/turnTrail.ts`.
 */

import { useState } from 'react';
import { ChevronDown, ChevronRight, Eye, Loader2 } from 'lucide-react';
import type { MessagePart } from '../../types/backend';
import { useAppStore } from '../../store/useAppStore';
import { useSessionRunIndex } from '../../runtime/runIndex';
import { tokenReadout } from '../../runtime/runInternals';
import {
  collapseRenderedMessageParts,
  countFailedToolParts,
  isToolPart,
  segmentTrail,
  splitTurn,
  summarizeToolParts,
  type ToolPart,
  type TrailSegment,
} from '../../runtime/turnTrail';
import { ChatMarkdown } from '../ChatMarkdown';
import { InlineToolPart } from './InlineToolRows';

/** The turn's token readout, straight from the run record: provider-reported usage
 *  when the provider gave one, the tokenizer estimate (marked ~) otherwise, and
 *  nothing at all while the run is still in flight. Lives in the thread because
 *  "how big was that" is asked of a message, not of a debugging panel. */
export function TurnTokenReadout({ sessionKey, runId }: { sessionKey: string; runId: string }) {
  const index = useSessionRunIndex(sessionKey);
  const run = index.byRunId.get(runId);
  const readout = run ? tokenReadout(run) : null;
  if (!readout) return null;
  return (
    <span
      className="shrink-0 font-mono text-[10px] tabular-nums text-operator-muted/55"
      title={run?.tokenUsage
        ? `Provider-reported: ${run.tokenUsage.modelCalls} model call${run.tokenUsage.modelCalls === 1 ? '' : 's'}, ${run.tokenUsage.inputTokens ?? '?'} input tokens billed in total`
        : 'Tokenizer estimate of the message history; the provider reported no usage'}
    >
      {readout}
    </span>
  );
}

/** The turn's internals, as one quiet row closing the message.
 *
 *  Load-bearing on a chat-only turn: that is exactly where "why didn't it use a
 *  tool?" gets asked, and `promptedToolUse: false` is the most common answer. It
 *  closes every settled turn, tools or not, because what the model was given is a
 *  fact about the whole turn rather than one more action inside it. */
export function TurnContextRow({ sessionKey, runId }: { sessionKey: string; runId: string }) {
  const setInspectorTarget = useAppStore((state) => state.setInspectorTarget);
  return (
    <button
      type="button"
      onClick={() => setInspectorTarget({ kind: 'run', sessionKey, runId })}
      className="inline-flex max-w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-[10px] text-operator-muted/55 transition-colors duration-100 hover:bg-operator-panel/20 hover:text-operator-muted"
      title="What this turn was given, and why it stopped"
    >
      <Eye className="h-2.5 w-2.5 shrink-0" />
      <span className="truncate">Context it saw</span>
      <TurnTokenReadout sessionKey={sessionKey} runId={runId} />
    </button>
  );
}

/** A quiet text header that discloses a bordered body. Shared by the per-burst
 *  tool group and the settled trail box so both read as the same object. */
function Disclosure({
  header,
  failed,
  busy,
  children,
}: {
  header: string;
  failed: number;
  busy?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex max-w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-[12px] text-operator-muted/80 transition-colors duration-100 hover:text-operator-text"
      >
        {busy && <Loader2 className="h-3 w-3 shrink-0 animate-spin text-operator-accent/70" />}
        <span className="min-w-0 truncate">{header}</span>
        {failed > 0 && <span className="shrink-0 text-[10px] text-operator-error">{failed} failed</span>}
        {open
          ? <ChevronDown className="h-3 w-3 shrink-0 text-operator-muted/50" />
          : <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/50" />}
      </button>
      {open && (
        <div className="mt-1 rounded-lg border border-operator-border/50 px-1.5 py-1">
          {children}
        </div>
      )}
    </div>
  );
}

/** Consecutive tool calls. One call is a bare row — a group of one is a wrapper
 *  around nothing. */
function ToolGroup({ parts, isLive, busy }: { parts: ToolPart[]; isLive?: boolean; busy?: boolean }) {
  if (parts.length === 1 && parts[0].kind !== 'tool_batch') {
    return <InlineToolPart part={parts[0]} isLive={isLive} />;
  }
  return (
    <Disclosure header={summarizeToolParts(parts)} failed={countFailedToolParts(parts)} busy={busy}>
      {parts.map((part, index) => (
        <InlineToolPart key={`tool-${index}`} part={part} isLive={isLive} />
      ))}
    </Disclosure>
  );
}

function TrailSegments({ segments, isLive }: { segments: TrailSegment[]; isLive?: boolean }) {
  const lastIndex = segments.length - 1;
  return (
    <div className="space-y-2">
      {segments.map((segment, index) => {
        const trailing = !!isLive && index === lastIndex;
        if (segment.kind === 'text') return <ChatMarkdown key={`text-${index}`} content={segment.part.content} />;
        if (segment.kind === 'thinking') {
          // Live only while it is the trailing part; it settles to one line as
          // soon as a tool row or text streams in after it.
          return <InlineToolPart key={`thinking-${index}`} part={segment.part} active={trailing} />;
        }
        return <ToolGroup key={`tools-${index}`} parts={segment.parts} isLive={isLive} busy={trailing} />;
      })}
    </div>
  );
}

export function TurnTrail({
  parts,
  isLive,
  sessionKey,
  runId,
}: {
  parts: MessagePart[];
  isLive?: boolean;
  sessionKey: string;
  runId: string | null;
}) {
  const renderParts = collapseRenderedMessageParts(parts);

  if (isLive) return <TrailSegments segments={segmentTrail(renderParts)} isLive />;

  const { trail, answer } = splitTurn(renderParts);
  const toolParts = trail.filter(isToolPart);
  return (
    <div className="space-y-2">
      {toolParts.length > 0 ? (
        <Disclosure header={summarizeToolParts(toolParts)} failed={countFailedToolParts(toolParts)}>
          <div className="px-1 py-1 text-[12.5px] text-operator-text/85">
            <TrailSegments segments={segmentTrail(trail)} />
          </div>
        </Disclosure>
      ) : (
        // Reasoning with no actions is not worth a box; it keeps its own row.
        trail.length > 0 && <TrailSegments segments={segmentTrail(trail)} />
      )}
      {answer.map((part, index) => (
        part.content ? <ChatMarkdown key={`answer-${index}`} content={part.content} /> : null
      ))}
      {runId && <TurnContextRow sessionKey={sessionKey} runId={runId} />}
    </div>
  );
}
