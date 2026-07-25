import { useEffect, useMemo, useRef, useState } from 'react';
import { AgentsWorkspaceSurface } from './AgentsWorkspaceSurface';
import { RightPanel } from './RightPanel';
import { SessionSidebar } from './SessionSidebar';
import { SessionDrawer } from './SessionDrawer';
import { InspectorDrawer } from './runtime/InspectorDrawer';
import { useIsMobile } from '../lib/responsive';
import { useAppStore } from '../store/useAppStore';
import { MobileSheet } from './mobile/MobileSheet';
import { PanelLeft, SlidersHorizontal } from 'lucide-react';
import { FleetInspector } from './fleet/FleetInspector';

const RIGHT_MIN = 270;
const RIGHT_MAX = 420;
const CENTER_MIN = 520;
const HANDLE_WIDTH = 8;
const RIGHT_DEFAULT = 340;
const RIGHT_WIDTH_STORAGE_KEY = 'copenet.agents.rightPaneWidth';

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function AgentsPage() {
  const isMobile = useIsMobile();
  const mobileSessionsOpen = useAppStore((state) => state.mobileSessionsOpen);
  const setMobileSessionsOpen = useAppStore((state) => state.setMobileSessionsOpen);
  const mobileInspectorOpen = useAppStore((state) => state.mobileInspectorOpen);
  const setMobileInspectorOpen = useAppStore((state) => state.setMobileInspectorOpen);
  const rightPanelOpen = useAppStore((state) => state.rightPanelOpen);
  const agentsWorkspaceMode = useAppStore((state) => state.agentsWorkspaceMode);
  const setRightPanelOpen = useAppStore((state) => state.setRightPanelOpen);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT);

  useEffect(() => {
    if (!isMobile && !rightPanelOpen) {
      setRightPanelOpen(true);
    }
  }, [isMobile, rightPanelOpen, setRightPanelOpen]);

  useEffect(() => {
    if (isMobile || typeof window === 'undefined') return;
    const storedRight = Number.parseFloat(window.localStorage.getItem(RIGHT_WIDTH_STORAGE_KEY) || '');
    if (Number.isFinite(storedRight)) {
      setRightWidth(storedRight);
    }
  }, [isMobile]);

  useEffect(() => {
    if (isMobile || typeof window === 'undefined') return;
    window.localStorage.setItem(RIGHT_WIDTH_STORAGE_KEY, String(rightWidth));
  }, [isMobile, rightWidth]);

  useEffect(() => {
    if (isMobile) return;
    const node = stageRef.current;
    if (!node || typeof ResizeObserver === 'undefined') return;

    const sync = () => {
      const width = node.clientWidth;
      const maxRight = Math.max(RIGHT_MIN, Math.min(RIGHT_MAX, width - CENTER_MIN - HANDLE_WIDTH));
      setRightWidth((current) => clamp(current, RIGHT_MIN, maxRight));
    };

    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(node);
    return () => observer.disconnect();
  }, [isMobile]);

  const startResize = (event: React.PointerEvent<HTMLDivElement>) => {
    if (isMobile) return;
    const node = stageRef.current;
    if (!node) return;

    event.preventDefault();
    const startX = event.clientX;
    const startRight = rightWidth;
    const stageWidth = node.clientWidth;

    const onMove = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX;
      const nextRight = clamp(
        startRight - delta,
        RIGHT_MIN,
        Math.max(RIGHT_MIN, Math.min(RIGHT_MAX, stageWidth - CENTER_MIN - HANDLE_WIDTH)),
      );
      setRightWidth(nextRight);
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };

    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
  };

  const resetResize = () => {
    setRightWidth(RIGHT_DEFAULT);
  };

  const desktopGrid = useMemo(
    () => ({
      gridTemplateColumns: `minmax(0,1fr) ${HANDLE_WIDTH}px ${rightPanelOpen ? rightWidth : 44}px`,
    }),
    [rightPanelOpen, rightWidth],
  );

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

          <div className="shell-operator-pane shell-operator-pane--main min-h-0 flex-1">
            <AgentsWorkspaceSurface />
          </div>
        </div>

        <MobileSheet open={mobileSessionsOpen} onClose={() => setMobileSessionsOpen(false)} title="Sessions" fullHeight>
          <SessionSidebar mobile onNavigate={() => setMobileSessionsOpen(false)} />
        </MobileSheet>

        <MobileSheet open={mobileInspectorOpen} onClose={() => setMobileInspectorOpen(false)} title="Inspector" fullHeight>
          {agentsWorkspaceMode === 'fleet' ? <FleetInspector mobile /> : <RightPanel mobile />}
        </MobileSheet>

        <InspectorDrawer />
      </>
    );
  }

  return (
    <>
      <div ref={stageRef} className="shell-operator-stage relative h-full" style={desktopGrid}>
        <div className="shell-operator-pane shell-operator-pane--main min-h-0 flex-1">
          <AgentsWorkspaceSurface />
        </div>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize inspector panel"
          onPointerDown={startResize}
          onDoubleClick={resetResize}
          className="group relative h-full cursor-col-resize"
          title="Drag to resize. Double-click to reset."
        >
          <div className="pointer-events-none absolute inset-y-1.5 left-1/2 w-px -translate-x-1/2 bg-shell-border/70 transition-colors duration-150 group-hover:bg-shell-accent/75 group-active:bg-shell-accent" />
        </div>
        <div className="shell-operator-pane shell-operator-pane--inspector min-h-0 shrink-0">
          {agentsWorkspaceMode === 'fleet' ? <FleetInspector /> : <RightPanel overviewOnly />}
        </div>
        <SessionDrawer />
      </div>
      <InspectorDrawer />
    </>
  );
}
