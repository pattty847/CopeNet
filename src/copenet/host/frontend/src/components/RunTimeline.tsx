import {
  AlertCircle,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  ExternalLink,
  Pause,
  Play,
  Settings2,
  ShieldAlert,
  ShieldCheck,
  X,
  Zap,
} from 'lucide-react';
import { useState } from 'react';
import { useRunTimeline, useMockTransitions } from '../runtime/adapter';
import { useAppStore } from '../store/useAppStore';
import type { RunTimelineEvent, RunTimelineEventKind, RunTimelineEventStatus } from '../runtime/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeLabel(iso: string) {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
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
// Event kind metadata
// ---------------------------------------------------------------------------

type EventMeta = {
  icon: typeof Play;
  iconColor: string;
  dotColor: string;
  lineColor: string;
};

const EVENT_META: Record<RunTimelineEventKind, EventMeta> = {
  run_started: {
    icon: Play,
    iconColor: 'text-operator-success',
    dotColor: 'bg-operator-success',
    lineColor: 'bg-operator-border',
  },
  tool_called: {
    icon: Settings2,
    iconColor: 'text-operator-muted',
    dotColor: 'bg-operator-muted/40',
    lineColor: 'bg-operator-border',
  },
  tool_result: {
    icon: Check,
    iconColor: 'text-operator-success',
    dotColor: 'bg-operator-success/40',
    lineColor: 'bg-operator-border',
  },
  approval_requested: {
    icon: ShieldAlert,
    iconColor: 'text-operator-error',
    dotColor: 'bg-operator-error',
    lineColor: 'bg-operator-error/30',
  },
  decision_made: {
    icon: ShieldCheck,
    iconColor: 'text-operator-success',
    dotColor: 'bg-operator-success',
    lineColor: 'bg-operator-border',
  },
  run_resumed: {
    icon: Play,
    iconColor: 'text-operator-success',
    dotColor: 'bg-operator-success',
    lineColor: 'bg-operator-border',
  },
  run_completed: {
    icon: CheckCircle2,
    iconColor: 'text-operator-success',
    dotColor: 'bg-operator-success',
    lineColor: 'bg-operator-border',
  },
  run_failed: {
    icon: AlertCircle,
    iconColor: 'text-operator-error',
    dotColor: 'bg-operator-error',
    lineColor: 'bg-operator-error/30',
  },
  note: {
    icon: ExternalLink,
    iconColor: 'text-operator-muted',
    dotColor: 'bg-operator-muted/30',
    lineColor: 'bg-operator-border',
  },
};

// ---------------------------------------------------------------------------
// Status overlay colors
// ---------------------------------------------------------------------------

const STATUS_RING: Record<RunTimelineEventStatus, string> = {
  ok: '',
  pending: 'ring-1 ring-operator-accent/50',
  paused: 'ring-2 ring-operator-error/60 animate-pulse',
  error: 'ring-1 ring-operator-error/50',
  skipped: 'opacity-40',
};

// ---------------------------------------------------------------------------
// Single timeline event row
// ---------------------------------------------------------------------------

function TimelineEventRow({
  event,
  isLast,
}: {
  event: RunTimelineEvent;
  isLast: boolean;
}) {
  const [expanded, setExpanded] = useState(event.status === 'paused');
  const meta = EVENT_META[event.kind];
  const Icon = meta.icon;
  const isPause = event.kind === 'approval_requested';
  const setRightPanelTab = useAppStore((s) => s.setRightPanelTab);

  return (
    <div className="flex gap-2.5">
      {/* Timeline spine */}
      <div className="flex flex-col items-center shrink-0" style={{ width: 20 }}>
        <div
          className={`flex h-5 w-5 items-center justify-center rounded-full shrink-0 z-10 ${
            isPause
              ? 'bg-operator-error/15 border-2 border-operator-error/50'
              : 'bg-operator-panel border border-operator-border'
          } ${STATUS_RING[event.status]}`}
        >
          <Icon className={`w-2.5 h-2.5 ${meta.iconColor}`} />
        </div>
        {!isLast && (
          <div className={`w-px flex-1 mt-0.5 min-h-[12px] ${isPause ? 'bg-operator-error/30' : 'bg-operator-border'}`} />
        )}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 pb-3">
        {/* Row header */}
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="w-full text-left group"
        >
          <div className="flex items-start gap-1.5">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <span
                  className={`text-[11px] font-semibold leading-snug ${
                    isPause ? 'text-operator-error' : 'text-operator-text'
                  }`}
                >
                  {event.label}
                </span>
                {event.durationMs != null && (
                  <span className="text-[9px] text-operator-muted/50 font-mono">
                    {event.durationMs}ms
                  </span>
                )}
              </div>
              {event.detail && !expanded && (
                <div className="text-[10px] text-operator-muted truncate mt-0.5">
                  {event.detail}
                </div>
              )}
            </div>
            <div className="flex items-center gap-1 shrink-0">
              <span className="text-[9px] font-mono text-operator-muted/50">
                {timeLabel(event.at)}
              </span>
              {event.detail && (
                <span className="text-operator-muted/40 group-hover:text-operator-muted transition-colors">
                  {expanded ? <ChevronUp className="w-2.5 h-2.5" /> : <ChevronDown className="w-2.5 h-2.5" />}
                </span>
              )}
            </div>
          </div>
        </button>

        {/* Expanded detail */}
        {expanded && event.detail && (
          <div className="mt-1.5 space-y-1.5">
            <div className="text-[11px] text-operator-muted leading-relaxed">
              {event.detail}
            </div>

            {/* Approval pause highlight */}
            {isPause && (
              <div className="rounded-lg border border-operator-error/30 bg-operator-error/6 px-3 py-2.5 space-y-1.5">
                <div className="flex items-center gap-1.5">
                  <Pause className="w-3 h-3 text-operator-error shrink-0" />
                  <span className="text-[11px] font-semibold text-operator-error">
                    Run paused here — waiting for your decision
                  </span>
                </div>
                <div className="text-[10px] text-operator-muted">
                  The agent proposed an action that requires operator approval before continuing.
                  Approve, reject, or modify in the Approvals tab.
                </div>
                <button
                  type="button"
                  onClick={() => setRightPanelTab('approvals')}
                  className="text-[10px] font-semibold text-operator-accent hover:underline"
                >
                  Open Approvals →
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pause callout — shown at bottom when run is currently paused
// ---------------------------------------------------------------------------

function PauseCallout({ approvalId }: { approvalId: string | null | undefined }) {
  const { simulateApprove, simulateReject } = useMockTransitions();
  const setRightPanelTab = useAppStore((s) => s.setRightPanelTab);
  return (
    <div className="rounded-xl border border-operator-error/35 bg-operator-error/6 px-3 py-3 space-y-2">
      <div className="flex items-center gap-2">
        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-operator-error/15 text-operator-error shrink-0">
          <Pause className="w-3 h-3 animate-pulse" />
        </div>
        <div>
          <div className="text-[12px] font-semibold text-operator-error">Run is paused</div>
          <div className="text-[10px] text-operator-muted">Waiting for your approval decision</div>
        </div>
      </div>
      <div className="flex gap-1.5">
        {approvalId && (
          <>
            <button
              type="button"
              onClick={() => simulateApprove(approvalId)}
              className="flex-1 inline-flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-semibold bg-operator-success/10 text-operator-success border border-operator-success/25 hover:bg-operator-success/20 transition-colors"
            >
              <Check className="w-3 h-3" /> Approve
            </button>
            <button
              type="button"
              onClick={() => simulateReject(approvalId)}
              className="flex-1 inline-flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-semibold bg-operator-error/8 text-operator-error border border-operator-error/20 hover:bg-operator-error/15 transition-colors"
            >
              <X className="w-3 h-3" /> Reject
            </button>
          </>
        )}
        <button
          type="button"
          onClick={() => setRightPanelTab('approvals')}
          className="px-3 py-1.5 rounded-lg text-[11px] font-semibold bg-operator-panel text-operator-muted border border-operator-border hover:text-operator-text hover:border-operator-accent/30 transition-colors"
        >
          Full view →
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function RunTimeline({ sessionKey }: { sessionKey: string | null }) {
  const timeline = useRunTimeline(sessionKey);
  const runPausedReason = useAppStore((s) => s.runPausedReason);
  const pendingApproval = useAppStore((s) => s.pendingApproval);
  const { simulateApprovalRequested } = useMockTransitions();

  if (!timeline) {
    // No paused run — show minimal placeholder
    return (
      <div className="px-3 py-3 space-y-2">
        <div className="flex items-center gap-2">
          <Zap className="w-3 h-3 text-operator-muted" />
          <span className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
            Run Timeline
          </span>
        </div>
        <div className="text-center py-5 space-y-1.5">
          <div className="text-[11px] text-operator-muted">No run paused</div>
          <div className="text-[10px] text-operator-muted/60">
            Timeline appears when a run is paused for approval.
          </div>
          <button
            type="button"
            onClick={() => simulateApprovalRequested()}
            className="mt-2 text-[10px] font-semibold text-operator-accent hover:underline"
          >
            Simulate paused run →
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="px-3 py-2.5 space-y-3">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Zap className="w-3.5 h-3.5 text-operator-muted" />
        <div className="flex-1 min-w-0">
          <span className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
            Run Timeline
          </span>
          <span className="text-[9px] font-mono text-operator-muted/50 ml-2">
            {timeline.runId.slice(-8)}
          </span>
        </div>
        {timeline.pausedAt && (
          <span className="text-[9px] font-semibold text-operator-error bg-operator-error/10 px-1.5 py-0.5 rounded border border-operator-error/20">
            paused {timeAgo(timeline.pausedAt)}
          </span>
        )}
      </div>

      {/* Pause callout */}
      {runPausedReason === 'awaiting_approval' && (
        <PauseCallout approvalId={pendingApproval?.approvalId} />
      )}

      {/* Events */}
      <div className="space-y-0">
        {timeline.events.map((event, idx) => (
          <TimelineEventRow
            key={event.id}
            event={event}
            isLast={idx === timeline.events.length - 1}
          />
        ))}
      </div>

      {/* Still-paused indicator at end */}
      {timeline.pausedAt && !timeline.resumedAt && (
        <div className="flex gap-2.5">
          <div className="flex flex-col items-center shrink-0" style={{ width: 20 }}>
            <div className="flex h-5 w-5 items-center justify-center rounded-full bg-operator-error/15 border border-dashed border-operator-error/40 shrink-0">
              <Clock className="w-2.5 h-2.5 text-operator-error animate-pulse" />
            </div>
          </div>
          <div className="flex-1 py-0.5">
            <div className="text-[10px] text-operator-error font-medium">
              Waiting for decision…
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
