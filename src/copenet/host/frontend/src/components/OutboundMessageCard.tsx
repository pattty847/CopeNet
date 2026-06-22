import { AlertCircle, Check, Clock, ExternalLink, Send, ShieldCheck } from 'lucide-react';
import { formatOutboundAge } from '../lib/formatting';
import type { OutboundMessageRecord, OutboundMessageStatus } from '../runtime/types';

const STATUS_META: Record<
  OutboundMessageStatus,
  { label: string; icon: typeof Check; tone: string; bg: string }
> = {
  drafted: { label: 'Draft', icon: Clock, tone: 'text-operator-muted', bg: 'bg-operator-panel' },
  pending_approval: { label: 'Awaiting Approval', icon: Clock, tone: 'text-operator-accent', bg: 'bg-operator-accent/10' },
  approved: { label: 'Approved', icon: ShieldCheck, tone: 'text-operator-success', bg: 'bg-operator-success/10' },
  sent: { label: 'Sent', icon: Check, tone: 'text-operator-success', bg: 'bg-operator-success/10' },
  failed: { label: 'Failed', icon: AlertCircle, tone: 'text-operator-error', bg: 'bg-operator-error/10' },
};

interface OutboundMessageCardProps {
  outbound: OutboundMessageRecord;
  onOpenApproval?: (approvalId: string) => void;
}

export function OutboundMessageCard({ outbound, onOpenApproval }: OutboundMessageCardProps) {
  const meta = STATUS_META[outbound.status];
  const StatusIcon = meta.icon;

  return (
    <div className="group lift-sm rounded-xl border border-operator-border bg-operator-panel/40 overflow-hidden">
      <div className="flex items-start gap-2.5 px-3 py-2.5">
        <div className={`flex h-8 w-8 items-center justify-center rounded-lg shrink-0 ${meta.bg} ${meta.tone}`}>
          <Send className="w-3.5 h-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted">
              Outbound Message
            </span>
            <span className={`flex items-center gap-0.5 text-[9px] font-semibold uppercase tracking-wider ml-auto ${meta.tone}`}>
              <StatusIcon className="w-2.5 h-2.5" />
              {meta.label}
            </span>
          </div>
          <div className="flex items-center gap-1.5 mb-1">
            <span className="inline-flex items-center gap-1 rounded-md bg-operator-bg border border-operator-border px-1.5 py-0.5 text-[10px] font-mono text-operator-muted shrink-0">
              <Send className="w-2.5 h-2.5 shrink-0" />
              {outbound.targetDisplayName ?? outbound.target}
            </span>
            <span className="text-[9px] text-operator-muted/70 font-mono ml-auto">
              {formatOutboundAge(outbound.createdAt)}
            </span>
          </div>
          <div className="text-[11px] text-operator-text leading-relaxed break-words bg-operator-bg/60 rounded-lg px-2.5 py-2 border border-operator-border whitespace-pre-wrap">
            {outbound.messageText}
          </div>
          {outbound.failureReason && (
            <div className="mt-1.5 flex items-start gap-1.5 text-[11px] text-operator-error leading-relaxed">
              <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
              {outbound.failureReason}
            </div>
          )}
          {outbound.sentAt && (
            <div className="mt-1.5 text-[10px] text-operator-muted">
              Delivered {formatOutboundAge(outbound.sentAt)}
              {outbound.approvalId && ' · approval on record'}
            </div>
          )}
          {outbound.status === 'pending_approval' && outbound.approvalId && onOpenApproval && (
            <div className="mt-1.5">
              <button
                type="button"
                onClick={() => onOpenApproval(outbound.approvalId!)}
                className="inline-flex items-center gap-1 text-[10px] font-semibold text-operator-accent hover:underline"
              >
                <ExternalLink className="w-3 h-3" /> View approval request
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
