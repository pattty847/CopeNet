/**
 * LiveToolFeed — real-time tool execution visibility during an active run.
 *
 * Renders the in-progress tool call list as delta events stream in from the
 * backend. Each completed tool step appears as a chip with its state
 * (success / failed / blocked) and a one-line summary.
 *
 * When the run is active but no tool calls have arrived yet, shows a pulsing
 * "Agent thinking" indicator so the operator knows the agent is alive.
 *
 * When the run finishes, `RunActivityPanel` takes over with the full
 * historical record. This component only renders during `activeRunId != null`.
 *
 * Backend dependency:
 *   toolExecution payloads on delta/final WebSocket events feed this via
 *   wsClient → store.pushLiveToolCall(). The backend does not yet emit
 *   per-tool-call events in real time — each toolExecution reflects the most
 *   recently completed tool. A dedicated `tool:called` + `tool:result` event
 *   stream would allow showing 'queued' and 'running' states mid-execution.
 */

import { CheckCircle2, Loader2, Shield, Terminal, XCircle, Zap } from 'lucide-react';
import type { LiveToolCall, ToolExecutionState } from '../../runtime/types';
import { useLiveToolCalls } from '../../runtime/adapter';
import { useAppStore } from '../../store/useAppStore';

// ---------------------------------------------------------------------------
// State metadata
// ---------------------------------------------------------------------------

type StateMeta = {
  icon: typeof CheckCircle2;
  color: string;
  bg: string;
  border: string;
  label: string;
};

const STATE_META: Record<ToolExecutionState, StateMeta> = {
  queued: {
    icon: Loader2,
    color: 'text-operator-muted',
    bg: 'bg-operator-panel/40',
    border: 'border-operator-border',
    label: 'Queued',
  },
  running: {
    icon: Loader2,
    color: 'text-operator-accent',
    bg: 'bg-operator-accent/5',
    border: 'border-operator-accent/30',
    label: 'Running',
  },
  success: {
    icon: CheckCircle2,
    color: 'text-operator-success',
    bg: 'bg-operator-success/5',
    border: 'border-operator-success/20',
    label: 'Success',
  },
  blocked: {
    icon: Shield,
    color: 'text-amber-400',
    bg: 'bg-amber-400/5',
    border: 'border-amber-400/25',
    label: 'Blocked',
  },
  failed: {
    icon: XCircle,
    color: 'text-operator-error',
    bg: 'bg-operator-error/5',
    border: 'border-operator-error/20',
    label: 'Failed',
  },
};

// ---------------------------------------------------------------------------
// Single tool chip
// ---------------------------------------------------------------------------

function ToolChip({ call }: { call: LiveToolCall }) {
  const meta = STATE_META[call.state];
  const Icon = meta.icon;
  const isSpinning = call.state === 'running' || call.state === 'queued';

  return (
    <div
      className={`flex items-start gap-2 rounded-lg border px-2.5 py-1.5 ${meta.bg} ${meta.border} transition-all duration-200 animate-fade-in-up`}
    >
      <Icon
        className={`w-3 h-3 shrink-0 mt-0.5 ${meta.color} ${isSpinning ? 'animate-spin' : ''}`}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[11px] text-operator-text font-medium shrink-0">
            {call.toolId}
          </span>
          <span
            className={`text-[9px] font-semibold uppercase tracking-wider ${meta.color} shrink-0`}
          >
            {meta.label}
          </span>
        </div>
        {call.summary && (
          <div className="text-[11px] text-operator-muted leading-snug mt-0.5 truncate">
            {call.summary}
          </div>
        )}
        {call.error && (
          <div className="text-[10px] text-operator-error leading-snug mt-0.5 font-mono truncate">
            {call.error}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Thinking indicator (no tool calls yet, run is active)
// ---------------------------------------------------------------------------

function ThinkingStrip() {
  return (
    <div className="flex items-center gap-2.5 rounded-lg border border-operator-accent/20 bg-operator-accent/5 px-3 py-2">
      <span className="relative flex h-2 w-2 shrink-0">
        <span className="absolute inline-flex h-full w-full rounded-full bg-operator-accent opacity-75 animate-ping" />
        <span className="relative inline-flex h-2 w-2 rounded-full bg-operator-accent" />
      </span>
      <span className="text-[12px] text-operator-accent font-medium">Agent thinking…</span>
      <Loader2 className="w-3 h-3 text-operator-accent/60 animate-spin ml-auto" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Turn summary chips after run completes
// ---------------------------------------------------------------------------

function TurnSummaryStrip({ callCount, failedCount }: { callCount: number; failedCount: number }) {
  const allGood = failedCount === 0;
  return (
    <div className="flex items-center gap-2 pt-1">
      <span className="text-[10px] text-operator-muted">Turn complete ·</span>
      <span className="font-mono text-[10px] text-operator-text">
        {callCount} tool{callCount !== 1 ? 's' : ''}
      </span>
      {failedCount > 0 && (
        <span className="text-[10px] text-operator-error font-mono">
          {failedCount} failed
        </span>
      )}
      {allGood && callCount > 0 && (
        <span className="text-[10px] text-operator-success">all ok</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// LiveToolFeed
// ---------------------------------------------------------------------------

export function LiveToolFeed() {
  const activeRunId = useAppStore((s) => s.activeRunId);
  const liveToolCalls = useLiveToolCalls();

  // Not rendered when no run is active
  if (!activeRunId) return null;

  const failedCount = liveToolCalls.filter(
    (c) => c.state === 'failed' || c.state === 'blocked',
  ).length;

  return (
    <div className="space-y-1.5">
      {/* Section header */}
      <div className="flex items-center gap-2 px-3 pt-2.5 pb-0.5">
        <Zap className="w-3 h-3 text-operator-accent" />
        <span className="text-[10px] font-semibold uppercase tracking-wider text-operator-accent">
          Live · Tool Activity
        </span>
        {liveToolCalls.length > 0 && (
          <span className="ml-auto font-mono text-[10px] text-operator-muted">
            {liveToolCalls.length} call{liveToolCalls.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      <div className="px-3 pb-2.5 space-y-1.5">
        {/* Thinking indicator when no calls yet */}
        {liveToolCalls.length === 0 && <ThinkingStrip />}

        {/* Tool chips: most recent last (append order = natural order) */}
        {liveToolCalls.map((call) => (
          <ToolChip key={call.id} call={call} />
        ))}

        {/* Run progress hint — always show "live" indicator at the bottom */}
        {liveToolCalls.length > 0 && (
          <div className="flex items-center gap-1.5 pt-0.5">
            <span className="relative flex h-1.5 w-1.5 shrink-0">
              <span className="absolute inline-flex h-full w-full rounded-full bg-operator-accent opacity-75 animate-ping" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-operator-accent" />
            </span>
            <span className="text-[10px] text-operator-muted">run in progress</span>
          </div>
        )}
      </div>

      {/* Show turn summary row when run finishes (activeRunId clears) — this won't render
          since the component bails early when activeRunId is null. Kept as reminder:
          TurnSummaryStrip should be shown in RunActivityPanel after the run record loads. */}
      {false && <TurnSummaryStrip callCount={liveToolCalls.length} failedCount={failedCount} />}
    </div>
  );
}

// Exported for use in RunActivityPanel's post-run footer
export { TurnSummaryStrip };

// Small utility for rendering a single tool execution chip inline (e.g. in
// chat messages that carry a toolExecution payload).
export function InlineToolChip({ toolId, ok, summary }: { toolId: string; ok: boolean; summary: string }) {
  const state: ToolExecutionState = ok ? 'success' : 'failed';
  const meta = STATE_META[state];
  const Icon = meta.icon;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-mono border ${meta.bg} ${meta.border}`}
    >
      <Icon className={`w-2.5 h-2.5 shrink-0 ${meta.color}`} />
      <span className="text-operator-text">{toolId}</span>
      {summary && (
        <span className={`${meta.color} truncate max-w-[180px]`}>{summary}</span>
      )}
    </span>
  );
}

// Re-export Terminal icon for use by parent components that need a tool icon
export { Terminal };
