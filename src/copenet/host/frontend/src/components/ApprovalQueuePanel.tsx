import { useState } from 'react';
import {
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  History,
  Pencil,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useApprovalHistory, useApprovalActions } from '../runtime/adapter';
import { useAppStore } from '../store/useAppStore';
import type { ApprovalRequest, ApprovalStatus } from '../runtime/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

const STATUS_META: Record<
  ApprovalStatus,
  { label: string; icon: typeof Check; tone: string; bg: string }
> = {
  pending: {
    label: 'Awaiting',
    icon: Clock,
    tone: 'text-operator-accent',
    bg: 'bg-operator-accent/10',
  },
  approved: {
    label: 'Approved',
    icon: ShieldCheck,
    tone: 'text-operator-success',
    bg: 'bg-operator-success/10',
  },
  rejected: {
    label: 'Rejected',
    icon: X,
    tone: 'text-operator-error',
    bg: 'bg-operator-error/8',
  },
  modified: {
    label: 'Modified',
    icon: Pencil,
    tone: 'text-operator-accent',
    bg: 'bg-operator-accent/10',
  },
  expired: {
    label: 'Expired',
    icon: Clock,
    tone: 'text-operator-muted',
    bg: 'bg-operator-panel',
  },
};

// ---------------------------------------------------------------------------
// Single row in the queue/history list
// ---------------------------------------------------------------------------

function ApprovalRow({ approval, defaultExpanded = false }: { approval: ApprovalRequest; defaultExpanded?: boolean }) {
  const [expanded, setExpanded] = useState(defaultExpanded);
  const { approve, reject } = useApprovalActions();
  const meta = STATUS_META[approval.status];
  const StatusIcon = meta.icon;
  const isPending = approval.status === 'pending';

  return (
    <div
      className={`rounded-xl border overflow-hidden ${isPending ? 'border-operator-accent/35 shadow-sm' : 'border-operator-border'}`}
    >
      {/* Row header */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2.5 px-3 py-2.5 text-left hover:bg-operator-panel/30 transition-colors duration-150"
      >
        <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg mt-0.5 ${meta.bg} ${meta.tone}`}>
          <StatusIcon className="w-3 h-3" />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className={`text-[9px] font-semibold uppercase tracking-wider ${meta.tone}`}>
              {meta.label}
            </span>
            <span className="text-[9px] text-operator-muted/70 font-mono ml-auto">
              {timeAgo(approval.createdAt)}
            </span>
          </div>
          <div className="text-[12px] font-semibold text-operator-text leading-snug truncate">
            {approval.toolId}
            {approval.proposedAction.target && (
              <span className="text-operator-muted font-normal ml-1">→ {approval.proposedAction.target.split(':').slice(1).join(':')}</span>
            )}
          </div>
          <div className="text-[10px] text-operator-muted truncate mt-0.5">
            {approval.proposedAction.description}
          </div>
        </div>
        <span className="shrink-0 text-operator-muted mt-1">
          {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </span>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="px-3 pb-2.5 pt-0 border-t border-operator-border/50 space-y-2">
          {/* Message payload */}
          {approval.proposedAction.payload?.message && (
            <div className="mt-2">
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                Message
              </div>
              <div className="text-[11px] text-operator-text bg-operator-bg rounded-lg px-2.5 py-2 border border-operator-border leading-relaxed whitespace-pre-wrap break-words">
                {String(approval.proposedAction.payload.message)}
              </div>
            </div>
          )}

          {/* Rationale */}
          {approval.rationale && (
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                Why
              </div>
              <div className="text-[11px] text-operator-muted leading-relaxed italic">
                {approval.rationale}
              </div>
            </div>
          )}

          {/* Outcome (resolved) */}
          {approval.outcome && (
            <div className="rounded-lg border border-operator-border bg-operator-bg/60 px-2.5 py-2 space-y-0.5">
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted">
                Decision
              </div>
              <div className={`text-[11px] font-semibold ${meta.tone}`}>
                {approval.outcome.decision.charAt(0).toUpperCase() + approval.outcome.decision.slice(1)}
              </div>
              {approval.outcome.note && (
                <div className="text-[11px] text-operator-muted">"{approval.outcome.note}"</div>
              )}
              {approval.resolvedAt && (
                <div className="text-[10px] text-operator-muted/60 font-mono">
                  {timeAgo(approval.resolvedAt)}
                </div>
              )}
              {approval.outcome.modifiedPayload?.message && (
                <div className="mt-1 pt-1 border-t border-operator-border/50">
                  <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">Modified message</div>
                  <div className="text-[11px] text-operator-text bg-operator-panel/40 rounded px-2 py-1.5 leading-relaxed whitespace-pre-wrap break-words">
                    {String(approval.outcome.modifiedPayload.message)}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Quick-action buttons for pending */}
          {isPending && (
            <div className="flex gap-1.5 pt-1">
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); approve(approval.approvalId); }}
                className="flex-1 inline-flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-semibold bg-operator-success/10 text-operator-success border border-operator-success/25 hover:bg-operator-success/20 transition-colors"
              >
                <Check className="w-3 h-3" /> Approve
              </button>
              <button
                type="button"
                onClick={(e) => { e.stopPropagation(); reject(approval.approvalId); }}
                className="flex-1 inline-flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-semibold bg-operator-error/8 text-operator-error border border-operator-error/20 hover:bg-operator-error/15 transition-colors"
              >
                <X className="w-3 h-3" /> Reject
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function ApprovalQueuePanel({ sessionKey }: { sessionKey: string | null }) {
  const history = useApprovalHistory(sessionKey);
  const [showHistory, setShowHistory] = useState(true);

  const pending = history.filter((r) => r.status === 'pending');
  const resolved = history.filter((r) => r.status !== 'pending');

  return (
    <div className="px-3 py-2.5 space-y-3">
      {/* Pending queue */}
      <section>
        <div className="flex items-center gap-1.5 mb-2">
          <ShieldAlert className="w-3 h-3 text-operator-accent" />
          <h3 className="text-[10px] font-semibold uppercase tracking-wider text-operator-accent">
            Pending · {pending.length}
          </h3>
        </div>
        {pending.length === 0 ? (
          <div className="text-[11px] text-operator-muted text-center py-3 rounded-xl border border-operator-border bg-operator-panel/20">
            No pending approvals
          </div>
        ) : (
          <div className="space-y-1.5">
            {pending.map((r) => (
              <ApprovalRow key={r.approvalId} approval={r} defaultExpanded />
            ))}
          </div>
        )}
      </section>

      {/* History */}
      <section>
        <button
          type="button"
          onClick={() => setShowHistory((v) => !v)}
          className="flex items-center gap-1.5 mb-2 group w-full"
        >
          <History className="w-3 h-3 text-operator-muted group-hover:text-operator-text transition-colors" />
          <h3 className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted group-hover:text-operator-text transition-colors">
            History · {resolved.length}
          </h3>
          <span className="ml-auto text-operator-muted group-hover:text-operator-text transition-colors">
            {showHistory ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </span>
        </button>
        {showHistory && (
          resolved.length === 0 ? (
            <div className="text-[11px] text-operator-muted text-center py-3 rounded-xl border border-operator-border bg-operator-panel/20">
              No resolved approvals yet
            </div>
          ) : (
            <div className="space-y-1.5 stagger-children">
              {resolved.map((r) => (
                <ApprovalRow key={r.approvalId} approval={r} />
              ))}
            </div>
          )
        )}
      </section>
    </div>
  );
}
