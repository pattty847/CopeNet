import { AlertTriangle, ChevronRight, Pause } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { useIsMobile } from '../lib/responsive';

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
  const setMobileInspectorOpen = useAppStore((s) => s.setMobileInspectorOpen);
  const isMobile = useIsMobile();

  if (runPausedReason !== 'awaiting_approval') return null;

  const toolLabel = pendingApproval?.toolId ?? 'action';
  const actionClass = pendingApproval?.actionClass ?? '';

  // On mobile the approval card renders inline below this banner, but also open
  // the Inspector sheet so the full runtime context is one tap away. On desktop
  // the card lives in the right-panel Runtime tab.
  const openApprovalPanel = () => {
    setRightPanelTab('runtime');
    if (isMobile) {
      setMobileInspectorOpen(true);
    } else {
      setRightPanelOpen(true);
    }
  };

  return (
    <button
      type="button"
      onClick={openApprovalPanel}
      className="group flex w-full items-center gap-2.5 border-b border-operator-accent/25 bg-operator-accent/6 px-4 py-2 text-left transition-colors duration-150 hover:bg-operator-accent/12"
    >
      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-operator-accent/15 text-operator-accent">
        <Pause className="h-3 w-3 fill-current" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12px] leading-snug text-operator-text">
          <span className="font-semibold text-operator-accent">Approval needed</span>
          <span className="text-operator-muted/70"> · </span>
          <span className="font-mono text-operator-text/85">{toolLabel}</span>
          {actionClass && (
            <span className="text-operator-muted/85"> ({actionClass.replace(/_/g, ' ')})</span>
          )}
        </span>
      </span>
      <span className="flex shrink-0 items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-operator-accent opacity-80 transition-opacity group-hover:opacity-100">
        <AlertTriangle className="h-3 w-3" />
        Review
        <ChevronRight className="h-3 w-3" />
      </span>
    </button>
  );
}
