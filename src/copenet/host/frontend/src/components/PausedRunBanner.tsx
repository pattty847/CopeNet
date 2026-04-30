import { AlertTriangle, ChevronRight, Pause } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';

/**
 * Sticky banner shown at the top of ChatWorkspace when a run is paused
 * waiting for operator approval. Clicking it opens the Runtime tab so the
 * operator can see and act on the pending ApprovalRequestCard.
 */
export function PausedRunBanner() {
  const runPausedReason = useAppStore((s) => s.runPausedReason);
  const pendingApproval = useAppStore((s) => s.pendingApproval);
  const setRightPanelTab = useAppStore((s) => s.setRightPanelTab);
  const setRightPanelOpen = useAppStore((s) => s.setRightPanelOpen);

  if (runPausedReason !== 'awaiting_approval') return null;

  const toolLabel = pendingApproval?.toolId ?? 'action';
  const actionClass = pendingApproval?.actionClass ?? '';

  const openApprovalPanel = () => {
    setRightPanelTab('runtime');
    setRightPanelOpen(true);
  };

  return (
    <button
      type="button"
      onClick={openApprovalPanel}
      className="group w-full flex items-center gap-2.5 px-4 py-2.5 bg-operator-accent/8 border-b border-operator-accent/25 text-left transition-colors duration-150 hover:bg-operator-accent/12"
    >
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-operator-accent/15 text-operator-accent">
        <Pause className="w-3 h-3 fill-current" />
      </span>
      <span className="flex-1 min-w-0">
        <span className="block text-[12px] font-semibold text-operator-accent leading-snug">
          Run paused — approval required
        </span>
        <span className="block text-[11px] text-operator-muted leading-snug truncate">
          Agent wants to run <span className="font-mono">{toolLabel}</span>
          {actionClass ? ` (${actionClass.replace(/_/g, ' ')})` : ''}. Review in the Inspector.
        </span>
      </span>
      <span className="flex items-center gap-1 text-[10px] font-semibold text-operator-accent uppercase tracking-wider shrink-0 opacity-70 group-hover:opacity-100 transition-opacity">
        <AlertTriangle className="w-3 h-3" />
        Review
        <ChevronRight className="w-3 h-3" />
      </span>
    </button>
  );
}
