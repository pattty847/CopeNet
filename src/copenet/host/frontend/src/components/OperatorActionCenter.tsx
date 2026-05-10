import {
  AlertCircle,
  Check,
  CheckCheck,
  ChevronDown,
  ChevronUp,
  Clock,
  History,
  Inbox,
  Pause,
  Pencil,
  Sparkles,
  ShieldAlert,
  ShieldCheck,
  X,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { wsClient } from '../lib/wsClient';
import { useInboxItems, useMockTransitions } from '../runtime/adapter';
import { useAppStore } from '../store/useAppStore';
import type { InboxItem, InboxItemPriority } from '../runtime/types';

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

const PRIORITY_META: Record<InboxItemPriority, { border: string; bg: string; glow: string }> = {
  urgent: {
    border: 'border-operator-error/40',
    bg: 'bg-operator-error/5',
    glow: 'shadow-sm shadow-operator-error/10',
  },
  attention: {
    border: 'border-operator-accent/35',
    bg: 'bg-operator-accent/5',
    glow: 'shadow-sm shadow-operator-accent/10',
  },
  info: {
    border: 'border-operator-border',
    bg: '',
    glow: '',
  },
};

// ---------------------------------------------------------------------------
// Individual inbox item row
// ---------------------------------------------------------------------------

function InboxItemRow({
  item,
  pulseSelected,
  onTogglePulseSelection,
  onSavePulse,
  onDismissPulse,
}: {
  item: InboxItem;
  pulseSelected: boolean;
  onTogglePulseSelection: (pulseId: string) => void;
  onSavePulse: (pulseIds: string[]) => Promise<void>;
  onDismissPulse: (pulseId: string) => Promise<void>;
}) {
  const [expanded, setExpanded] = useState(item.priority === 'urgent' || item.kind === 'pulse');
  const [pulseBusy, setPulseBusy] = useState<'save' | 'dismiss' | null>(null);
  const { simulateApprove, simulateReject } = useMockTransitions();
  const setRightPanelTab = useAppStore((s) => s.setRightPanelTab);
  const style = PRIORITY_META[item.priority];

  const isPaused = item.kind === 'paused_run';
  const isPending = item.kind === 'pending_approval' || isPaused;
  const isResolved = item.kind === 'resolved_approval' || item.kind === 'sent_message';
  const isFailed = item.kind === 'failed_send';

  const isPulse = item.kind === 'pulse';
  const StatusIcon =
    isPulse ? Sparkles
    : isPaused ? Pause
    : item.kind === 'pending_approval' ? ShieldAlert
    : item.approvalData?.status === 'approved' ? ShieldCheck
    : item.approvalData?.status === 'modified' ? Pencil
    : item.approvalData?.status === 'rejected' ? X
    : item.approvalData?.status === 'expired' ? Clock
    : isFailed ? AlertCircle
    : Check;

  const statusTone =
    isPulse ? 'text-operator-accent'
    : isPaused ? 'text-operator-error'
    : item.kind === 'pending_approval' ? 'text-operator-accent'
    : item.approvalData?.status === 'approved' ? 'text-operator-success'
    : item.approvalData?.status === 'modified' ? 'text-operator-accent'
    : item.approvalData?.status === 'rejected' ? 'text-operator-error'
    : item.approvalData?.status === 'expired' ? 'text-operator-muted'
    : isFailed ? 'text-operator-error'
    : 'text-operator-success';

  const statusLabel =
    isPulse ? 'Pulse ready'
    : isPaused ? 'Run paused'
    : item.kind === 'pending_approval' ? 'Awaiting decision'
    : item.approvalData?.status === 'approved' ? 'Approved'
    : item.approvalData?.status === 'modified' ? 'Modified & sent'
    : item.approvalData?.status === 'rejected' ? 'Rejected'
    : item.approvalData?.status === 'expired' ? 'Expired'
    : isFailed ? 'Failed'
    : 'Resolved';

  return (
    <div className={`rounded-xl border overflow-hidden ${style.border} ${style.bg} ${style.glow}`}>
      {/* Header row */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2.5 px-3 py-2.5 text-left hover:bg-operator-panel/20 transition-colors duration-150"
      >
        <span className={`shrink-0 mt-0.5 ${statusTone}`}>
          <StatusIcon className={`w-3.5 h-3.5 ${isPaused || item.kind === 'pending_approval' ? 'animate-pulse' : ''}`} />
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className={`text-[9px] font-semibold uppercase tracking-wider ${statusTone}`}>
              {statusLabel}
            </span>
            <span className="text-[9px] text-operator-muted/60 font-mono ml-auto shrink-0">
              {timeAgo(item.createdAt)}
            </span>
          </div>
          <div className="text-[12px] font-semibold text-operator-text leading-snug truncate">
            {item.title}
          </div>
          <div className="text-[10px] text-operator-muted truncate mt-0.5">
            {item.subtitle}
          </div>
        </div>
        <span className="shrink-0 text-operator-muted mt-1">
          {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
        </span>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div className="border-t border-operator-border/40 px-3 pb-3 pt-2 space-y-2">
          {/* Message payload */}
          {item.approvalData?.proposedAction.payload?.message && (
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                Message
              </div>
              <div className="text-[11px] text-operator-text bg-operator-bg rounded-lg px-2.5 py-2 border border-operator-border leading-relaxed whitespace-pre-wrap break-words max-h-28 overflow-y-auto">
                {String(item.approvalData.proposedAction.payload.message)}
              </div>
            </div>
          )}

          {isPulse && item.pulseData && (
            <div className="space-y-2">
              <div>
                <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                  Summary
                </div>
                <div className="text-[11px] text-operator-text leading-relaxed">
                  {item.pulseData.summary}
                </div>
              </div>
              {item.pulseData.sourceSessions.length > 0 && (
                <div>
                  <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                    Source sessions
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {item.pulseData.sourceSessions.map((source) => (
                      <span
                        key={`${item.pulseData!.pulseId}:${source.sessionKey}`}
                        className="rounded-full border border-operator-border px-2 py-0.5 text-[10px] text-operator-muted"
                      >
                        {source.title}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onTogglePulseSelection(item.pulseData!.pulseId);
                  }}
                  className={`rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-colors ${
                    pulseSelected
                      ? 'border-operator-accent/30 bg-operator-accent/10 text-operator-accent'
                      : 'border-operator-border text-operator-muted hover:text-operator-text'
                  }`}
                >
                  {pulseSelected ? 'Selected' : 'Select'}
                </button>
                <button
                  type="button"
                  disabled={pulseBusy !== null}
                  onClick={async (e) => {
                    e.stopPropagation();
                    setPulseBusy('save');
                    try {
                      await onSavePulse([item.pulseData!.pulseId]);
                    } finally {
                      setPulseBusy(null);
                    }
                  }}
                  className="rounded-lg border border-operator-accent/25 bg-operator-accent/10 px-2.5 py-1.5 text-[11px] font-semibold text-operator-accent transition-colors hover:bg-operator-accent/15 disabled:opacity-40"
                >
                  {pulseBusy === 'save' ? 'Saving…' : 'Save'}
                </button>
                <button
                  type="button"
                  disabled={pulseBusy !== null}
                  onClick={async (e) => {
                    e.stopPropagation();
                    setPulseBusy('dismiss');
                    try {
                      await onDismissPulse(item.pulseData!.pulseId);
                    } finally {
                      setPulseBusy(null);
                    }
                  }}
                  className="rounded-lg border border-operator-border px-2.5 py-1.5 text-[11px] font-semibold text-operator-muted transition-colors hover:text-operator-text disabled:opacity-40"
                >
                  {pulseBusy === 'dismiss' ? 'Dismissing…' : 'Dismiss'}
                </button>
              </div>
            </div>
          )}

          {/* Rationale */}
          {item.approvalData?.rationale && (
            <div>
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                Why
              </div>
              <div className="text-[11px] text-operator-muted italic leading-relaxed">
                {item.approvalData.rationale}
              </div>
            </div>
          )}

          {/* Outcome (resolved) */}
          {isResolved && item.approvalData?.outcome && (
            <div className="rounded-lg border border-operator-border bg-operator-bg/60 px-2.5 py-2 space-y-0.5">
              <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted">
                Decision
              </div>
              <div className={`text-[11px] font-semibold ${statusTone}`}>
                {item.approvalData.outcome.decision.charAt(0).toUpperCase() +
                  item.approvalData.outcome.decision.slice(1)}
              </div>
              {item.approvalData.outcome.note && (
                <div className="text-[11px] text-operator-muted">
                  "{item.approvalData.outcome.note}"
                </div>
              )}
              {item.approvalData.outcome.modifiedPayload?.message && (
                <div className="mt-1 pt-1 border-t border-operator-border/50">
                  <div className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted mb-1">
                    Modified message
                  </div>
                  <div className="text-[11px] text-operator-text bg-operator-panel/40 rounded px-2 py-1.5 leading-relaxed">
                    {String(item.approvalData.outcome.modifiedPayload.message)}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Quick actions for urgent/pending */}
          {isPending && item.approvalData && (
            <div className="flex gap-1.5 pt-0.5">
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  simulateApprove(item.approvalData!.approvalId);
                }}
                className="flex-1 inline-flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-semibold bg-operator-success/10 text-operator-success border border-operator-success/25 hover:bg-operator-success/20 transition-colors"
              >
                <Check className="w-3 h-3" /> Approve
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  simulateReject(item.approvalData!.approvalId);
                }}
                className="flex-1 inline-flex items-center justify-center gap-1 py-1.5 rounded-lg text-[11px] font-semibold bg-operator-error/8 text-operator-error border border-operator-error/20 hover:bg-operator-error/15 transition-colors"
              >
                <X className="w-3 h-3" /> Reject
              </button>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setRightPanelTab('approvals');
                }}
                title="Open full approval view"
                className="px-2.5 py-1.5 rounded-lg text-[11px] font-semibold bg-operator-panel text-operator-muted border border-operator-border hover:text-operator-text hover:border-operator-accent/30 transition-colors"
              >
                Detail →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function AllClearBanner() {
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-10 text-center">
      <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-operator-success/8 text-operator-success">
        <CheckCheck className="h-4 w-4" />
      </div>
      <div className="text-[12.5px] font-medium text-operator-text">All clear</div>
      <div className="max-w-[200px] text-[11.5px] leading-relaxed text-operator-muted/85">
        Nothing waiting on you right now.
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main action center
// ---------------------------------------------------------------------------

export function OperatorActionCenter({ sessionKey }: { sessionKey: string | null }) {
  const items = useInboxItems(sessionKey);
  const [showHistory, setShowHistory] = useState(true);
  const [selectedPulseIds, setSelectedPulseIds] = useState<string[]>([]);
  const draftSettings = useAppStore((s) => s.draftSettings);
  const upsertSession = useAppStore((s) => s.upsertSession);
  const setActiveSessionKey = useAppStore((s) => s.setActiveSessionKey);
  const setDraftOpen = useAppStore((s) => s.setDraftOpen);
  const setCurrentSection = useAppStore((s) => s.setCurrentSection);
  const setMergeState = useAppStore((s) => s.setMergeState);
  const setAppError = useAppStore((s) => s.setAppError);
  const pulseItems = useMemo(() => items.filter((item) => item.kind === 'pulse' && item.pulseData), [items]);

  const urgentItems = items.filter((i) => i.priority === 'urgent');
  const attentionItems = items.filter((i) => i.priority === 'attention' && i.kind !== 'pulse');
  const pulseAttentionItems = items.filter((i) => i.kind === 'pulse');
  const historyItems = items.filter((i) => i.priority === 'info');
  const actionRequired = urgentItems.length + attentionItems.length + pulseAttentionItems.length;

  const togglePulseSelection = (pulseId: string) => {
    setSelectedPulseIds((current) =>
      current.includes(pulseId) ? current.filter((item) => item !== pulseId) : [...current, pulseId],
    );
  };

  const handleSavePulseIds = async (pulseIds: string[]) => {
    try {
      const created = await wsClient.savePulses({
        pulseIds,
        provider: draftSettings.provider,
        model: draftSettings.model,
        systemPromptId: draftSettings.systemPromptId,
        taskPromptId: draftSettings.taskPromptId,
        workspaceRoot: draftSettings.workspaceRoot || '',
      });
      upsertSession(created.session);
      setActiveSessionKey(created.session.key);
      setDraftOpen(false);
      setCurrentSection('agents');
      setMergeState(created.session.key, created.mergeState);
      setSelectedPulseIds((current) => current.filter((id) => !pulseIds.includes(id)));
      await wsClient.loadHistory(created.session.key);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to save pulse.');
    }
  };

  const handleDismissPulse = async (pulseId: string) => {
    try {
      await wsClient.dismissPulse(pulseId);
      setSelectedPulseIds((current) => current.filter((id) => id !== pulseId));
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to dismiss pulse.');
    }
  };

  return (
    <div className="px-3 py-3 space-y-3">
      {actionRequired > 0 && (
        <div className="flex items-center gap-2 rounded-xl border border-operator-error/25 bg-operator-error/5 px-3 py-2 text-[11px]">
          <Inbox className="h-3 w-3 shrink-0 text-operator-error" />
          <span className="font-semibold text-operator-error">
            {actionRequired} item{actionRequired === 1 ? '' : 's'} need{actionRequired === 1 ? 's' : ''} your attention
          </span>
        </div>
      )}

      {/* Urgent section */}
      {urgentItems.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 mb-2">
            <Pause className="w-3 h-3 text-operator-error" />
            <h3 className="text-[10px] font-semibold uppercase tracking-wider text-operator-error">
              Run paused · {urgentItems.length}
            </h3>
          </div>
          <div className="space-y-1.5">
            {urgentItems.map((item) => (
              <InboxItemRow
                key={item.id}
                item={item}
                pulseSelected={false}
                onTogglePulseSelection={togglePulseSelection}
                onSavePulse={handleSavePulseIds}
                onDismissPulse={handleDismissPulse}
              />
            ))}
          </div>
        </section>
      )}

      {/* Attention section */}
      {attentionItems.length > 0 && (
        <section>
          <div className="flex items-center gap-1.5 mb-2">
            <ShieldAlert className="w-3 h-3 text-operator-accent" />
            <h3 className="text-[10px] font-semibold uppercase tracking-wider text-operator-accent">
              Pending approval · {attentionItems.length}
            </h3>
          </div>
          <div className="space-y-1.5">
            {attentionItems.map((item) => (
              <InboxItemRow
                key={item.id}
                item={item}
                pulseSelected={false}
                onTogglePulseSelection={togglePulseSelection}
                onSavePulse={handleSavePulseIds}
                onDismissPulse={handleDismissPulse}
              />
            ))}
          </div>
        </section>
      )}

      {/* All clear */}
      {urgentItems.length === 0 && attentionItems.length === 0 && pulseItems.length === 0 && <AllClearBanner />}

      {pulseItems.length > 0 && (
        <section>
          <div className="mb-2 flex items-center gap-1.5">
            <Sparkles className="w-3 h-3 text-operator-accent" />
            <h3 className="text-[10px] font-semibold uppercase tracking-wider text-operator-accent">
              Pulses · {pulseItems.length}
            </h3>
            {selectedPulseIds.length > 1 && (
              <button
                type="button"
                onClick={() => void handleSavePulseIds(selectedPulseIds)}
                className="ml-auto rounded-lg border border-operator-accent/25 bg-operator-accent/10 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-operator-accent"
              >
                Save {selectedPulseIds.length} to Workspace
              </button>
            )}
          </div>
          <div className="space-y-1.5">
            {pulseItems.map((item) => (
              <InboxItemRow
                key={item.id}
                item={item}
                pulseSelected={Boolean(item.pulseData && selectedPulseIds.includes(item.pulseData.pulseId))}
                onTogglePulseSelection={togglePulseSelection}
                onSavePulse={handleSavePulseIds}
                onDismissPulse={handleDismissPulse}
              />
            ))}
          </div>
        </section>
      )}

      {/* History section */}
      {historyItems.length > 0 && (
        <section>
          <button
            type="button"
            onClick={() => setShowHistory((v) => !v)}
            className="flex items-center gap-1.5 mb-2 group w-full"
          >
            <History className="w-3 h-3 text-operator-muted group-hover:text-operator-text transition-colors" />
            <h3 className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted group-hover:text-operator-text transition-colors">
              Recent · {historyItems.length}
            </h3>
            <span className="ml-auto text-operator-muted group-hover:text-operator-text transition-colors">
              {showHistory ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            </span>
          </button>
          {showHistory && (
            <div className="space-y-1.5">
              {historyItems.map((item) => (
                <InboxItemRow
                  key={item.id}
                  item={item}
                  pulseSelected={false}
                  onTogglePulseSelection={togglePulseSelection}
                  onSavePulse={handleSavePulseIds}
                  onDismissPulse={handleDismissPulse}
                />
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
