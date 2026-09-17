import { useEffect, useMemo, useRef, useState } from 'react';
import { AgentsWorkspaceSurface } from './AgentsWorkspaceSurface';
import { RightPanel } from './RightPanel';
import { SessionSidebar } from './SessionSidebar';
import { SessionDrawer } from './SessionDrawer';
import { InspectorDrawer } from './runtime/InspectorDrawer';
import { useIsMobile } from '../lib/responsive';
import { useAppStore } from '../store/useAppStore';
import { MobileSheet } from './mobile/MobileSheet';
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
        {/* No chrome row of its own: the Sessions and Inspector buttons render inside the
            workspace's title row (see AgentsMobileChrome), so the phone has one bar rather
            than three. The sheets they open still belong to this page. */}
        <div className="flex h-full min-h-0 flex-col">
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
