import { useState } from 'react';
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronUp,
  MessageSquare,
  Pencil,
  Send,
  ShieldAlert,
  X,
} from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import type { ApprovalRequest } from '../runtime/types';

const ACTION_CLASS_LABELS: Record<string, { label: string; icon: typeof ShieldAlert; tone: string }> = {
  external_communication: { label: 'External Communication', icon: Send, tone: 'text-operator-accent' },
  filesystem_write: { label: 'File System Write', icon: Pencil, tone: 'text-operator-warning' },
  process_execution: { label: 'Process Execution', icon: ShieldAlert, tone: 'text-operator-error' },
  network_side_effect: { label: 'Network Side Effect', icon: ShieldAlert, tone: 'text-operator-warning' },
  credential_or_sensitive_target: { label: 'Sensitive Target', icon: ShieldAlert, tone: 'text-operator-error' },
};

interface ApprovalRequestCardProps {
  approval: ApprovalRequest;
}

export function ApprovalRequestCard({ approval }: ApprovalRequestCardProps) {
  const resolveApproval = useAppStore((s) => s.resolveApproval);
  const [expanded, setExpanded] = useState(false);
  const [modifyMode, setModifyMode] = useState(false);
  const [modifiedMessage, setModifiedMessage] = useState(
    (approval.proposedAction.payload?.message as string | undefined) ?? '',
  );
  const [note, setNote] = useState('');

  const isPending = approval.status === 'pending';
  const meta = ACTION_CLASS_LABELS[approval.actionClass] ?? {
    label: approval.actionClass,
    icon: ShieldAlert,
    tone: 'text-operator-muted',
  };
  const MetaIcon = meta.icon;

  const decide = (decision: 'approved' | 'rejected' | 'modified') => {
    const now = new Date().toISOString();
    resolveApproval(approval.approvalId, {
      decision,
      note: note || null,
      decidedAt: now,
      ...(decision === 'modified'
        ? {
            modifiedPayload: {
              ...approval.proposedAction.payload,
              message: modifiedMessage,
            },
          }
        : {}),
    });
  };

  const statusBadge = () => {
    if (approval.status === 'approved') return <span className="text-[10px] font-semibold text-operator-success uppercase tracking-wider">Approved</span>;
    if (approval.status === 'rejected') return <span className="text-[10px] font-semibold text-operator-error uppercase tracking-wider">Rejected</span>;
    if (approval.status === 'modified') return <span className="text-[10px] font-semibold text-operator-accent uppercase tracking-wider">Modified</span>;
    if (approval.status === 'expired') return <span className="text-[10px] font-semibold text-operator-muted uppercase tracking-wider">Expired</span>;
    return (
      <span className="flex items-center gap-1 text-[10px] font-semibold text-operator-accent uppercase tracking-wider animate-pulse">
        <span className="h-1.5 w-1.5 rounded-full bg-operator-accent inline-block" />
        Awaiting
      </span>
    );
  };

  return (
    <div className={`rounded-xl border overflow-hidden ${isPending ? 'border-operator-accent/40 bg-operator-accent/5' : 'border-operator-border bg-operator-panel/40'}`}>
      {/* Header */}
      <div className="flex items-start gap-2.5 px-3 py-2.5">
        <div className={`flex h-8 w-8 items-center justify-center rounded-lg shrink-0 bg-operator-accent/10 ${meta.tone}`}>
          <MetaIcon className="w-3.5 h-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">
              Approval Request
            </span>
            <span className={`text-[9px] font-medium uppercase tracking-wider ${meta.tone} ml-auto`}>
              {meta.label}
            </span>
          </div>
          <div className="text-[12px] font-semibold text-operator-text leading-snug mb-0.5">
            {approval.toolId}
          </div>
          <div className="text-[11px] text-operator-muted leading-relaxed break-words">
            {approval.proposedAction.description}
          </div>
          {approval.proposedAction.target && (
            <div className="mt-1 inline-flex items-center gap-1 rounded-md bg-operator-bg border border-operator-border px-1.5 py-0.5 text-[10px] font-mono text-operator-muted">
              <Send className="w-2.5 h-2.5 shrink-0" />
              {approval.proposedAction.target}
            </div>
          )}
        </div>
        <div className="shrink-0 flex flex-col items-end gap-1 pt-0.5">
          {statusBadge()}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="text-operator-muted hover:text-operator-text transition-colors"
            title={expanded ? 'Collapse' : 'Expand'}
          >
            {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        </div>
      </div>

      {/* Expandable detail */}
      {expanded && (
        <div className="px-3 pb-2.5 space-y-2 border-t border-operator-border/60">
          {approval.rationale && (
            <div className="pt-2">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1 flex items-center gap-1">
                <MessageSquare className="w-3 h-3" /> Why
              </div>
              <div className="text-[11px] text-operator-text leading-relaxed bg-operator-bg/60 rounded-lg px-2.5 py-2 border border-operator-border">
                {approval.rationale}
              </div>
            </div>
          )}

          {approval.proposedAction.payload?.message && (
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1 flex items-center gap-1">
                <MessageSquare className="w-3 h-3" /> Message draft
              </div>
              {modifyMode ? (
                <textarea
                  value={modifiedMessage}
                  onChange={(e) => setModifiedMessage(e.target.value)}
                  rows={4}
                  className="w-full rounded-lg border border-operator-accent/30 bg-operator-bg px-2.5 py-2 text-[11px] text-operator-text leading-relaxed resize-none focus:outline-none focus:border-operator-accent/60"
                />
              ) : (
                <div className="text-[11px] text-operator-text leading-relaxed bg-operator-bg/60 rounded-lg px-2.5 py-2 border border-operator-border whitespace-pre-wrap break-words">
                  {approval.proposedAction.payload.message as string}
                </div>
              )}
            </div>
          )}

          {isPending && (
            <div>
              <label className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted block mb-1">
                Note (optional)
              </label>
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Reason, override, or context…"
                className="w-full rounded-lg border border-operator-border bg-operator-bg px-2.5 py-1.5 text-[11px] text-operator-text placeholder:text-operator-muted/50 focus:outline-none focus:border-operator-accent/40"
              />
            </div>
          )}

          {approval.outcome && (
            <div className="pt-1 text-[11px] text-operator-muted leading-relaxed">
              <span className="font-semibold">Decision: </span>
              {approval.outcome.decision}
              {approval.outcome.note && <span> · {approval.outcome.note}</span>}
            </div>
          )}
        </div>
      )}

      {/* Action strip — only shown for pending */}
      {isPending && (
        <div className="flex items-center gap-1 px-3 py-2 border-t border-operator-border/60 bg-operator-bg/40">
          <button
            type="button"
            onClick={() => decide('approved')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-operator-success/10 text-operator-success border border-operator-success/25 hover:bg-operator-success/20 transition-colors duration-150"
          >
            <Check className="w-3 h-3" /> Approve
          </button>
          <button
            type="button"
            onClick={() => decide('rejected')}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold bg-operator-error/8 text-operator-error border border-operator-error/20 hover:bg-operator-error/15 transition-colors duration-150"
          >
            <X className="w-3 h-3" /> Reject
          </button>
          {approval.proposedAction.payload?.message !== undefined && (
            <button
              type="button"
              onClick={() => {
                if (modifyMode) {
                  decide('modified');
                } else {
                  setModifyMode(true);
                  setExpanded(true);
                }
              }}
              className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-[11px] font-semibold text-operator-muted border border-operator-border hover:text-operator-text hover:border-operator-accent/30 transition-colors duration-150 ml-auto"
            >
              <Pencil className="w-3 h-3" />
              {modifyMode ? 'Send modified' : 'Modify'}
            </button>
          )}
          {modifyMode && (
            <button
              type="button"
              onClick={() => { setModifyMode(false); setModifiedMessage(approval.proposedAction.payload?.message as string ?? ''); }}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] text-operator-muted hover:text-operator-text transition-colors duration-150"
            >
              <AlertTriangle className="w-3 h-3" /> Cancel edit
            </button>
          )}
        </div>
      )}
    </div>
  );
}
