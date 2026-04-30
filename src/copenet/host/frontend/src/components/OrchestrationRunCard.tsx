import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Cpu,
  Link2,
  Loader2,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { useState } from 'react';
import type { OrchestrationRun, OrchestrationRunStatus } from '../runtime/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.floor(m / 60)}h ago`;
}

// ---------------------------------------------------------------------------
// Status metadata
// ---------------------------------------------------------------------------

type StatusMeta = {
  icon: typeof CheckCircle2;
  label: string;
  tone: string;
  bg: string;
  border: string;
};

const STATUS_META: Record<OrchestrationRunStatus, StatusMeta> = {
  pending: {
    icon: Clock,
    label: 'Pending',
    tone: 'text-operator-muted',
    bg: 'bg-operator-panel',
    border: 'border-operator-border',
  },
  running: {
    icon: Loader2,
    label: 'Running',
    tone: 'text-operator-accent',
    bg: 'bg-operator-accent/10',
    border: 'border-operator-accent/30',
  },
  completed: {
    icon: CheckCircle2,
    label: 'Completed',
    tone: 'text-operator-success',
    bg: 'bg-operator-success/10',
    border: 'border-operator-success/25',
  },
  failed: {
    icon: AlertCircle,
    label: 'Failed',
    tone: 'text-operator-error',
    bg: 'bg-operator-error/8',
    border: 'border-operator-error/25',
  },
  approval_required: {
    icon: ShieldAlert,
    label: 'Approval required',
    tone: 'text-operator-accent',
    bg: 'bg-operator-accent/10',
    border: 'border-operator-accent/35',
  },
  cancelled: {
    icon: AlertCircle,
    label: 'Cancelled',
    tone: 'text-operator-muted',
    bg: 'bg-operator-panel',
    border: 'border-operator-border',
  },
};

// ---------------------------------------------------------------------------
// Tool usage bar — visual budget indicator
// ---------------------------------------------------------------------------

function ToolBudgetBar({ used, budget }: { used: number; budget: number }) {
  const pct = Math.min(100, (used / budget) * 100);
  const tone =
    pct >= 90 ? 'bg-operator-error'
    : pct >= 70 ? 'bg-operator-accent'
    : 'bg-operator-success';

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-operator-border overflow-hidden">
        <div
          className={`h-full rounded-full ${tone} transition-all duration-500`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-[9px] font-mono text-operator-muted shrink-0">
        {used}/{budget}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main card
// ---------------------------------------------------------------------------

interface OrchestrationRunCardProps {
  run: OrchestrationRun;
}

export function OrchestrationRunCard({ run }: OrchestrationRunCardProps) {
  const [expanded, setExpanded] = useState(false);
  const meta = STATUS_META[run.status];
  const StatusIcon = meta.icon;
  const isRunning = run.status === 'running';

  return (
    <div className={`rounded-xl border overflow-hidden ${meta.border}`}>
      {/* Card header */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2.5 px-3 py-2.5 text-left hover:bg-operator-panel/30 transition-colors duration-150"
      >
        {/* Icon */}
        <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-lg mt-0.5 ${meta.bg} ${meta.tone}`}>
          <Cpu className="w-3.5 h-3.5" />
        </div>

        {/* Header text */}
        <div className="flex-1 min-w-0">
          {/* Status + timing row */}
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className={`flex items-center gap-0.5 text-[9px] font-semibold uppercase tracking-wider ${meta.tone}`}>
              <StatusIcon className={`w-2.5 h-2.5 ${isRunning ? 'animate-spin' : ''}`} />
              {meta.label}
            </span>
            {run.durationMs != null && (
              <span className="text-[9px] text-operator-muted/60 font-mono">
                {formatDuration(run.durationMs)}
              </span>
            )}
            <span className="text-[9px] text-operator-muted/50 font-mono ml-auto">
              {timeAgo(run.startedAt)}
            </span>
          </div>

          {/* Goal */}
          <div className="text-[12px] font-semibold text-operator-text leading-snug">
            {run.goal.length > 72 ? `${run.goal.slice(0, 69)}…` : run.goal}
          </div>

          {/* Quick stats row */}
          <div className="flex items-center gap-2 mt-1">
            <span className="flex items-center gap-0.5 text-[10px] text-operator-muted">
              <Zap className="w-2.5 h-2.5" />
              {run.toolCallsUsed} tool calls
            </span>
            {run.approvalRequired && (
              <span className="flex items-center gap-0.5 text-[9px] text-operator-accent">
                <ShieldAlert className="w-2.5 h-2.5" />
                Needed approval
              </span>
            )}
            {!run.approvalRequired && run.status === 'completed' && (
              <span className="flex items-center gap-0.5 text-[9px] text-operator-success">
                <ShieldCheck className="w-2.5 h-2.5" />
                Auto-run
              </span>
            )}
          </div>
        </div>

        <span className="shrink-0 text-operator-muted mt-1">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </span>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-operator-border/50 px-3 pb-3 pt-2.5 space-y-3">

          {/* Script summary */}
          {run.scriptSummary && (
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                Script logic
              </div>
              <div className="text-[11px] text-operator-muted leading-relaxed italic">
                {run.scriptSummary}
              </div>
            </div>
          )}

          {/* Tool budget */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted">
                Tool budget
              </div>
              <span className="text-[9px] text-operator-muted/60 font-mono">
                timeout {run.timeoutSeconds}s
              </span>
            </div>
            <ToolBudgetBar used={run.toolCallsUsed} budget={run.toolBudget} />
          </div>

          {/* Tools used breakdown */}
          {run.toolsUsed.length > 0 && (
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5">
                Tools used
              </div>
              <div className="space-y-1">
                {run.toolsUsed.map((tool, idx) => (
                  <div
                    key={idx}
                    className="flex items-start gap-2 rounded-lg bg-operator-panel/40 px-2.5 py-1.5"
                  >
                    <Settings2 className="w-2.5 h-2.5 text-operator-muted mt-0.5 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-[10px] font-mono font-semibold text-operator-text">
                          {tool.toolId}
                        </span>
                        <span className="text-[9px] text-operator-muted/70">
                          ×{tool.count}
                        </span>
                      </div>
                      <div className="text-[10px] text-operator-muted truncate">
                        {tool.summary}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Output summary */}
          {run.outputSummary && (
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                Output
              </div>
              <div className="text-[11px] text-operator-text bg-operator-bg rounded-lg px-2.5 py-2 border border-operator-border leading-relaxed">
                {run.outputSummary}
              </div>
            </div>
          )}

          {/* Related artifacts */}
          {run.relatedArtifactIds.length > 0 && (
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                Related artifacts
              </div>
              <div className="flex flex-wrap gap-1">
                {run.relatedArtifactIds.map((id) => (
                  <span
                    key={id}
                    className="flex items-center gap-1 text-[9px] font-mono text-operator-accent bg-operator-accent/8 border border-operator-accent/20 rounded px-1.5 py-0.5"
                  >
                    <Link2 className="w-2 h-2" />
                    {id}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Error state */}
          {run.error && (
            <div className="rounded-lg border border-operator-error/30 bg-operator-error/6 px-2.5 py-2">
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-error mb-0.5">
                Error
              </div>
              <div className="text-[11px] text-operator-error font-mono">
                {run.error}
              </div>
            </div>
          )}

          {/* Safety metadata footer */}
          <div className="flex items-center gap-3 pt-0.5 border-t border-operator-border/40">
            <span className="text-[9px] text-operator-muted/60 font-mono">
              id: {run.orchestrationId.slice(-8)}
            </span>
            <span className="text-[9px] text-operator-muted/60">
              Bounded run · safe helper tools only
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
