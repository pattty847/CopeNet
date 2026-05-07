import { useEffect, useMemo, useRef, useState } from 'react';
import { ChatWorkspace } from './ChatWorkspace';
import { RightPanel } from './RightPanel';
import { SessionSidebar } from './SessionSidebar';
import { InspectorDrawer } from './runtime/InspectorDrawer';
import { useIsMobile } from '../lib/responsive';
import { useAppStore } from '../store/useAppStore';
import { MobileSheet } from './mobile/MobileSheet';
import { PanelLeft, SlidersHorizontal } from 'lucide-react';

const LEFT_MIN = 248;
const LEFT_MAX = 420;
const RIGHT_MIN = 270;
const RIGHT_MAX = 420;
const CENTER_MIN = 520;
const HANDLE_WIDTH = 8;
const LEFT_DEFAULT = 320;
const RIGHT_DEFAULT = 340;
const LEFT_WIDTH_STORAGE_KEY = 'copenet.agents.leftPaneWidth';
const RIGHT_WIDTH_STORAGE_KEY = 'copenet.agents.rightPaneWidth';
const COLLAPSED_PANE_WIDTH = 44;

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

export function AgentsPage() {
  const isMobile = useIsMobile();
  const mobileSessionsOpen = useAppStore((state) => state.mobileSessionsOpen);
  const setMobileSessionsOpen = useAppStore((state) => state.setMobileSessionsOpen);
  const mobileInspectorOpen = useAppStore((state) => state.mobileInspectorOpen);
  const setMobileInspectorOpen = useAppStore((state) => state.setMobileInspectorOpen);
  const sidebarOpen = useAppStore((state) => state.sidebarOpen);
  const rightPanelOpen = useAppStore((state) => state.rightPanelOpen);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [leftWidth, setLeftWidth] = useState(LEFT_DEFAULT);
  const [rightWidth, setRightWidth] = useState(RIGHT_DEFAULT);

  useEffect(() => {
    if (isMobile || typeof window === 'undefined') return;
    const storedLeft = Number.parseFloat(window.localStorage.getItem(LEFT_WIDTH_STORAGE_KEY) || '');
    const storedRight = Number.parseFloat(window.localStorage.getItem(RIGHT_WIDTH_STORAGE_KEY) || '');
    if (Number.isFinite(storedLeft)) {
      setLeftWidth(storedLeft);
    }
    if (Number.isFinite(storedRight)) {
      setRightWidth(storedRight);
    }
  }, [isMobile]);

  useEffect(() => {
    if (isMobile || typeof window === 'undefined') return;
    window.localStorage.setItem(LEFT_WIDTH_STORAGE_KEY, String(leftWidth));
  }, [isMobile, leftWidth]);

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
      const maxLeft = Math.max(LEFT_MIN, Math.min(LEFT_MAX, width - RIGHT_MIN - CENTER_MIN - HANDLE_WIDTH * 2));
      const maxRight = Math.max(RIGHT_MIN, Math.min(RIGHT_MAX, width - leftWidth - CENTER_MIN - HANDLE_WIDTH * 2));
      setLeftWidth((current) => clamp(current, LEFT_MIN, maxLeft));
      setRightWidth((current) => clamp(current, RIGHT_MIN, maxRight));
    };

    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(node);
    return () => observer.disconnect();
  }, [isMobile, leftWidth]);

  const startResize = (side: 'left' | 'right') => (event: React.PointerEvent<HTMLDivElement>) => {
    if (isMobile) return;
    const node = stageRef.current;
    if (!node) return;

    event.preventDefault();
    const startX = event.clientX;
    const startLeft = leftWidth;
    const startRight = rightWidth;
    const stageWidth = node.clientWidth;

    const onMove = (moveEvent: PointerEvent) => {
      const delta = moveEvent.clientX - startX;
      if (side === 'left') {
        const nextLeft = clamp(
          startLeft + delta,
          LEFT_MIN,
          Math.max(LEFT_MIN, Math.min(LEFT_MAX, stageWidth - startRight - CENTER_MIN - HANDLE_WIDTH * 2)),
        );
        setLeftWidth(nextLeft);
        return;
      }

      const nextRight = clamp(
        startRight - delta,
        RIGHT_MIN,
        Math.max(RIGHT_MIN, Math.min(RIGHT_MAX, stageWidth - startLeft - CENTER_MIN - HANDLE_WIDTH * 2)),
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

  const resetResize = (side: 'left' | 'right') => () => {
    if (side === 'left') {
      setLeftWidth(LEFT_DEFAULT);
      return;
    }
    setRightWidth(RIGHT_DEFAULT);
  };

  const desktopGrid = useMemo(
    () => ({
      gridTemplateColumns: `${sidebarOpen ? leftWidth : COLLAPSED_PANE_WIDTH}px ${HANDLE_WIDTH}px minmax(0,1fr) ${HANDLE_WIDTH}px ${
        rightPanelOpen ? rightWidth : COLLAPSED_PANE_WIDTH
      }px`,
    }),
    [leftWidth, rightPanelOpen, rightWidth, sidebarOpen],
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
      <div ref={stageRef} className="shell-operator-stage h-full" style={desktopGrid}>
        <div className="shell-operator-pane shell-operator-pane--sidebar min-h-0 shrink-0">
          <SessionSidebar />
        </div>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize session sidebar"
          onPointerDown={startResize('left')}
          onDoubleClick={resetResize('left')}
          className="group relative h-full cursor-col-resize"
          title="Drag to resize. Double-click to reset."
        >
          <div className="pointer-events-none absolute inset-y-1.5 left-1/2 w-px -translate-x-1/2 bg-shell-border/70 transition-colors duration-150 group-hover:bg-shell-accent/75 group-active:bg-shell-accent" />
        </div>
        <div className="shell-operator-pane shell-operator-pane--main min-h-0 flex-1">
          <ChatWorkspace />
        </div>
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="Resize inspector panel"
          onPointerDown={startResize('right')}
          onDoubleClick={resetResize('right')}
          className="group relative h-full cursor-col-resize"
          title="Drag to resize. Double-click to reset."
        >
          <div className="pointer-events-none absolute inset-y-1.5 left-1/2 w-px -translate-x-1/2 bg-shell-border/70 transition-colors duration-150 group-hover:bg-shell-accent/75 group-active:bg-shell-accent" />
        </div>
        <div className="shell-operator-pane shell-operator-pane--inspector min-h-0 shrink-0">
          <RightPanel />
        </div>
      </div>
      <InspectorDrawer />
    </>
  );
}
