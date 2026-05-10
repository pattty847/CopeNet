import { createPortal } from 'react-dom';
import { useState } from 'react';
import {
  AlertCircle,
  Check,
  ChevronDown,
  Clock,
  Send,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { useDestinations, useMockTransitions } from '../runtime/adapter';
import type { MessageDestination } from '../types/backend';
import type { OutboundMessageStatus } from '../runtime/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PLATFORM_ICON: Record<string, string> = {
  telegram: '✈',
  slack: '#',
  discord: '◆',
};

const STATUS_META: Record<OutboundMessageStatus, { label: string; tone: string; icon: typeof Check }> = {
  drafted: { label: 'Drafted', tone: 'text-operator-muted', icon: Clock },
  pending_approval: { label: 'Awaiting Approval', tone: 'text-operator-accent', icon: ShieldAlert },
  approved: { label: 'Approved', tone: 'text-operator-success', icon: ShieldCheck },
  sent: { label: 'Sent', tone: 'text-operator-success', icon: Check },
  failed: { label: 'Failed', tone: 'text-operator-error', icon: AlertCircle },
};

// ---------------------------------------------------------------------------
// Destination picker dropdown
// ---------------------------------------------------------------------------

function DestinationSelect({
  destinations,
  value,
  onChange,
}: {
  destinations: MessageDestination[];
  value: string | null;
  onChange: (target: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = destinations.find((d) => d.target === value);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg border border-operator-border bg-operator-bg text-left hover:border-operator-accent/40 transition-colors duration-150 focus:outline-none focus:border-operator-accent/50"
      >
        {selected ? (
          <>
            <span className="text-[13px]">{PLATFORM_ICON[selected.platform] ?? '→'}</span>
            <span className="flex-1 min-w-0">
              <span className="text-[12px] font-medium text-operator-text block truncate">
                {selected.displayName}
              </span>
              {selected.threadLabel && (
                <span className="text-[10px] text-operator-muted">{selected.threadLabel}</span>
              )}
            </span>
            {selected.requiresApproval && (
              <span className="flex items-center gap-0.5 text-[9px] font-semibold uppercase tracking-wider text-operator-accent shrink-0">
                <ShieldAlert className="w-2.5 h-2.5" />
                Needs approval
              </span>
            )}
          </>
        ) : (
          <span className="text-[12px] text-operator-muted flex-1">Pick a destination…</span>
        )}
        <ChevronDown className="w-3.5 h-3.5 text-operator-muted shrink-0" />
      </button>

      {open && (
        <div className="absolute z-50 top-full mt-1 left-0 right-0 rounded-xl border border-operator-border bg-operator-bg shadow-lg overflow-hidden">
          {destinations.map((dest) => (
            <button
              key={dest.id}
              type="button"
              onClick={() => { onChange(dest.target); setOpen(false); }}
              className={`w-full flex items-center gap-2 px-2.5 py-2.5 text-left hover:bg-operator-panel/50 transition-colors duration-100 ${value === dest.target ? 'bg-operator-accent/8' : ''}`}
            >
              <span className="text-[13px] shrink-0">{PLATFORM_ICON[dest.platform] ?? '→'}</span>
              <span className="flex-1 min-w-0">
                <span className="text-[12px] font-medium text-operator-text block truncate">
                  {selected?.isDefault && dest.id === selected.id ? `${dest.displayName} (default)` : dest.displayName}
                </span>
                <span className="text-[10px] font-mono text-operator-muted truncate block">
                  {dest.target}
                  {dest.threadLabel ? ` · ${dest.threadLabel}` : ''}
                </span>
              </span>
              <span className="shrink-0 flex flex-col items-end gap-0.5">
                {dest.isDefault && (
                  <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted">Default</span>
                )}
                {dest.requiresApproval && (
                  <span className="flex items-center gap-0.5 text-[9px] font-semibold text-operator-accent">
                    <ShieldAlert className="w-2.5 h-2.5" />
                    Approval
                  </span>
                )}
                {!dest.requiresApproval && (
                  <span className="flex items-center gap-0.5 text-[9px] font-semibold text-operator-success">
                    <Check className="w-2.5 h-2.5" />
                    Direct
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status transition display
// ---------------------------------------------------------------------------

function StatusTrail({ status }: { status: OutboundMessageStatus | null }) {
  if (!status) return null;
  const steps: OutboundMessageStatus[] = ['drafted', 'pending_approval', 'approved', 'sent'];
  const currentIdx = steps.indexOf(status === 'failed' ? 'approved' : status);

  return (
    <div className="flex items-center gap-1">
      {steps.map((step, idx) => {
        const isCurrent = step === status || (status === 'failed' && step === 'approved');
        const isDone = idx < currentIdx;
        const isFailed = status === 'failed' && step === 'approved';
        const meta = STATUS_META[step];
        const Icon = meta.icon;
        return (
          <div key={step} className="flex items-center gap-1">
            <div className={`flex items-center gap-1 text-[9px] font-semibold uppercase tracking-wider ${
              isFailed ? 'text-operator-error' :
              isCurrent ? meta.tone :
              isDone ? 'text-operator-success' : 'text-operator-muted/40'
            }`}>
              <Icon className="w-2.5 h-2.5" />
              {step.replace(/_/g, ' ')}
            </div>
            {idx < steps.length - 1 && (
              <span className={`text-[9px] ${isDone ? 'text-operator-success' : 'text-operator-muted/30'}`}>→</span>
            )}
          </div>
        );
      })}
      {status === 'failed' && (
        <span className="text-[9px] font-semibold text-operator-error ml-1">FAILED</span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main composer
// ---------------------------------------------------------------------------

export function SendMessageComposer() {
  const composerOpen = useAppStore((s) => s.composerOpen);
  const composerTarget = useAppStore((s) => s.composerTarget);
  const composerMessage = useAppStore((s) => s.composerMessage);
  const setComposerOpen = useAppStore((s) => s.setComposerOpen);
  const setComposerTarget = useAppStore((s) => s.setComposerTarget);
  const setComposerMessage = useAppStore((s) => s.setComposerMessage);
  const resetComposer = useAppStore((s) => s.resetComposer);

  const destinations = useDestinations();
  const { simulateSendMessageComposed } = useMockTransitions();

  const [sendStatus, setSendStatus] = useState<OutboundMessageStatus | null>(null);
  const [lastMessage, setLastMessage] = useState<string>('');
  const [lastTarget, setLastTarget] = useState<string>('');

  const selectedDest = destinations.find((d) => d.target === composerTarget) ?? null;
  const needsApproval = selectedDest?.requiresApproval ?? true;
  const canSend = !!composerTarget && composerMessage.trim().length > 0;
  const charCount = composerMessage.length;
  const charLimit = 4096;

  const handleSend = () => {
    if (!canSend) return;
    setLastMessage(composerMessage);
    setLastTarget(composerTarget!);
    setSendStatus('drafted');

    const record = simulateSendMessageComposed(composerTarget!, composerMessage.trim());
    setSendStatus(record.status);
  };

  const handleClose = () => {
    setSendStatus(null);
    resetComposer();
  };

  if (!composerOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/45 backdrop-blur-sm"
        onClick={handleClose}
      />

      {/* Panel */}
      <div className="relative z-10 w-full max-w-lg rounded-2xl border border-operator-border bg-operator-bg shadow-shell-xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-2.5 px-4 py-3 border-b border-operator-border">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-operator-accent/10 text-operator-accent">
            <Send className="w-3.5 h-3.5" />
          </div>
          <div>
            <h2 className="text-[13px] font-semibold text-operator-text">Send Message</h2>
            <p className="text-[10px] text-operator-muted">Operator-initiated outbound message</p>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="ml-auto p-1.5 rounded-lg text-operator-muted hover:text-operator-text hover:bg-operator-panel transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="p-4 space-y-3">
          {/* Status trail when sent */}
          {sendStatus && (
            <div className="rounded-xl border border-operator-border bg-operator-panel/30 px-3 py-2.5 space-y-1.5">
              <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">Status</div>
              <StatusTrail status={sendStatus} />
              {sendStatus === 'pending_approval' && (
                <div className="text-[11px] text-operator-accent mt-1 flex items-center gap-1">
                  <ShieldAlert className="w-3 h-3 shrink-0" />
                  Approval request created — check the Approvals tab.
                </div>
              )}
              {sendStatus === 'sent' && (
                <div className="text-[11px] text-operator-success flex items-center gap-1">
                  <Check className="w-3 h-3 shrink-0" />
                  Delivered to {lastTarget.split(':').slice(1).join(':')}
                </div>
              )}
              {sendStatus === 'failed' && (
                <div className="text-[11px] text-operator-error flex items-center gap-1">
                  <AlertCircle className="w-3 h-3 shrink-0" />
                  Delivery failed — see Artifacts for details.
                </div>
              )}
              <button
                type="button"
                onClick={() => { setSendStatus(null); setComposerMessage(''); }}
                className="text-[10px] text-operator-muted hover:text-operator-text mt-1"
              >
                Compose another →
              </button>
            </div>
          )}

          {/* Composer form — hidden after send */}
          {!sendStatus && (
            <>
              {/* Destination */}
              <div>
                <label className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted block mb-1.5">
                  Destination
                </label>
                <DestinationSelect
                  destinations={destinations}
                  value={composerTarget}
                  onChange={setComposerTarget}
                />
              </div>

              {/* Approval preview */}
              {selectedDest && (
                <div className={`flex items-center gap-2 rounded-lg px-2.5 py-2 text-[11px] border ${
                  needsApproval
                    ? 'border-operator-accent/25 bg-operator-accent/6 text-operator-accent'
                    : 'border-operator-success/20 bg-operator-success/6 text-operator-success'
                }`}>
                  {needsApproval
                    ? <><ShieldAlert className="w-3 h-3 shrink-0" /> This destination requires operator approval before sending.</>
                    : <><ShieldCheck className="w-3 h-3 shrink-0" /> This destination sends directly — no approval required.</>
                  }
                </div>
              )}

              {/* Message body */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
                    Message
                  </label>
                  <span className={`text-[9px] font-mono ${charCount > charLimit ? 'text-operator-error' : 'text-operator-muted/60'}`}>
                    {charCount}/{charLimit}
                  </span>
                </div>
                <textarea
                  value={composerMessage}
                  onChange={(e) => setComposerMessage(e.target.value)}
                  rows={5}
                  placeholder="Type your message…"
                  className="w-full rounded-lg border border-operator-border bg-operator-bg px-2.5 py-2 text-[12px] text-operator-text placeholder:text-operator-muted/50 leading-relaxed resize-none focus:outline-none focus:border-operator-accent/40 transition-colors"
                />
              </div>

              {/* Action row */}
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={handleClose}
                  className="px-3 py-2 rounded-lg text-[11px] font-medium text-operator-muted border border-operator-border hover:text-operator-text hover:border-operator-accent/30 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSend}
                  disabled={!canSend || charCount > charLimit}
                  className={`flex-1 flex items-center justify-center gap-1.5 py-2 rounded-lg text-[12px] font-semibold transition-colors ${
                    canSend && charCount <= charLimit
                      ? needsApproval
                        ? 'bg-operator-accent/10 text-operator-accent border border-operator-accent/25 hover:bg-operator-accent/20'
                        : 'bg-operator-success/10 text-operator-success border border-operator-success/25 hover:bg-operator-success/20'
                      : 'bg-operator-panel text-operator-muted/50 border border-operator-border cursor-not-allowed'
                  }`}
                >
                  <Send className="w-3.5 h-3.5" />
                  {needsApproval ? 'Request approval to send' : 'Send now'}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>,
    document.body,
  );
}
