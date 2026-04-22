import { ChatWorkspace } from './ChatWorkspace';
import { RightPanel } from './RightPanel';
import { SessionSidebar } from './SessionSidebar';
import { InspectorDrawer } from './runtime/InspectorDrawer';
import { useIsMobile } from '../lib/responsive';
import { useAppStore } from '../store/useAppStore';
import { MobileSheet } from './mobile/MobileSheet';
import { PanelLeft, SlidersHorizontal } from 'lucide-react';

export function AgentsPage() {
  const isMobile = useIsMobile();
  const mobileSessionsOpen = useAppStore((state) => state.mobileSessionsOpen);
  const setMobileSessionsOpen = useAppStore((state) => state.setMobileSessionsOpen);
  const mobileInspectorOpen = useAppStore((state) => state.mobileInspectorOpen);
  const setMobileInspectorOpen = useAppStore((state) => state.setMobileInspectorOpen);

  if (isMobile) {
    return (
      <>
        <div className="flex h-full min-h-0 flex-col gap-2">
          <div className="sticky top-0 z-10 -mx-1 flex items-center gap-2 overflow-x-auto px-1 pb-1 pt-1">
            <button
              type="button"
              onClick={() => setMobileSessionsOpen(true)}
              className="inline-flex h-10 shrink-0 items-center gap-2 rounded-2xl border border-shell-border bg-shell-panel px-3 py-2 text-[12px] font-medium text-shell-text shadow-shell"
            >
              <PanelLeft className="h-4 w-4 text-shell-accent" />
              Sessions
            </button>
            <button
              type="button"
              onClick={() => setMobileInspectorOpen(true)}
              className="inline-flex h-10 shrink-0 items-center gap-2 rounded-2xl border border-shell-border bg-shell-panel px-3 py-2 text-[12px] font-medium text-shell-text shadow-shell"
            >
              <SlidersHorizontal className="h-4 w-4 text-shell-accent" />
              Inspector
            </button>
          </div>

          <div className="min-h-0 flex-1 overflow-hidden rounded-[18px] border border-shell-border bg-shell-operator-frame shadow-shell">
            <ChatWorkspace />
          </div>
        </div>

        <MobileSheet open={mobileSessionsOpen} onClose={() => setMobileSessionsOpen(false)} title="Sessions" fullHeight>
          <SessionSidebar mobile />
        </MobileSheet>

        <MobileSheet open={mobileInspectorOpen} onClose={() => setMobileInspectorOpen(false)} title="Inspector" fullHeight>
          <RightPanel mobile />
        </MobileSheet>

        <InspectorDrawer />
      </>
    );
  }

  return (
    <>
      <div className="flex h-full min-h-0 gap-2">
        <div className="min-h-0 shrink-0 overflow-hidden rounded-[18px] border border-shell-border bg-shell-operator-frame shadow-shell">
          <SessionSidebar />
        </div>
        <div className="min-h-0 flex-1 overflow-hidden rounded-[18px] border border-shell-border bg-shell-operator-frame shadow-shell">
          <ChatWorkspace />
        </div>
        <div className="min-h-0 shrink-0 overflow-hidden rounded-[18px] border border-shell-border bg-shell-operator-frame shadow-shell">
          <RightPanel />
        </div>
      </div>
      <InspectorDrawer />
    </>
  );
}
