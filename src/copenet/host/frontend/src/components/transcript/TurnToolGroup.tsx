/**
 * TurnToolGroup — every tool call in one assistant turn, as one collapsed group.
 *
 * The shape most agent surfaces converged on, and the one CopeNet was closest to
 * already: a single summary row per turn ("Searched 1 path, ran 1 command"),
 * expanding to one line per action, each line opening the full detail in the
 * InspectorDrawer overlay rather than inline.
 *
 * Why the detail is not inline: tool output is frequently a whole file or a long
 * command dump, and squeezing that between two chat messages makes the thread
 * unreadable. The overlay is 680px with its own scroll — the right place to read
 * something long. The thread keeps a stable, scannable height either way.
 *
 * The last row in the group is the turn's own internals, because "what the model
 * was given" is one more thing that happened in the turn, not a separate class of
 * object deserving its own panel. That framing is what let the earlier inline
 * internals panel disappear entirely.
 */

import { useState } from 'react';
import { ChevronDown, ChevronRight, Eye } from 'lucide-react';
import type { MessagePart } from '../../types/backend';
import { useAppStore } from '../../store/useAppStore';
import { operatorVerb } from './InlineToolRows';

/** Group header text: "Searched 1 path, ran 1 command". Counts by verb so the
 *  summary stays short no matter how many calls a turn made. */
export function summarizeToolParts(parts: MessagePart[]): string {
  const counts = new Map<string, number>();
  for (const part of parts) {
    if (part.kind !== 'tool_result' && part.kind !== 'tool_call' && part.kind !== 'tool_batch') continue;
    const toolId = 'toolId' in part ? part.toolId : 'tool.batch';
    const verb = operatorVerb(toolId).toLowerCase();
    counts.set(verb, (counts.get(verb) || 0) + 1);
  }
  if (counts.size === 0) return 'No tools used';
  const phrases = [...counts.entries()].map(([verb, count]) => `${verb} ${count}×`);
  const joined = phrases.join(', ');
  return joined.charAt(0).toUpperCase() + joined.slice(1);
}

/** The turn's internals as one bare row, for a turn that called no tools.
 *
 *  Load-bearing: a chat-only turn is exactly the case where "why didn't it use a
 *  tool?" gets asked, and `promptedToolUse: false` is the most common answer.
 *  Hiding the row when there is nothing to group would hide it precisely where
 *  it matters most. */
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
    </button>
  );
}

export function TurnToolGroup({
  sessionKey,
  runId,
  parts,
  children,
  defaultOpen = false,
}: {
  sessionKey: string;
  runId: string | null;
  parts: MessagePart[];
  children: React.ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const setInspectorTarget = useAppStore((state) => state.setInspectorTarget);

  const failed = parts.filter((part) => part.kind === 'tool_result' && !part.ok).length;

  return (
    <div className="overflow-hidden rounded-lg border border-operator-border/50">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left transition-colors duration-100 hover:bg-operator-panel/25"
      >
        {open
          ? <ChevronDown className="h-3 w-3 shrink-0 text-operator-muted/50" />
          : <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/50" />}
        <span className="min-w-0 flex-1 truncate text-[11px] text-operator-muted/85">
          {summarizeToolParts(parts)}
        </span>
        {failed > 0 && <span className="shrink-0 text-[10px] text-operator-error">{failed} failed</span>}
      </button>

      {open && (
        <div className="border-t border-operator-border/40 px-1.5 py-1">
          {children}
          {runId && (
            <button
              type="button"
              onClick={() => setInspectorTarget({ kind: 'run', sessionKey, runId })}
              className="flex w-full items-center gap-2 rounded px-1 py-1 text-left transition-colors duration-100 hover:bg-operator-panel/20"
            >
              <Eye className="h-3 w-3 shrink-0 text-operator-muted/45" />
              <span className="min-w-0 flex-1 truncate text-[11px] text-operator-muted/75">
                Context it saw, and why it stopped
              </span>
              <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/40" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}
