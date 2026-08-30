// The bottom dock.
//
// This is the structural bet: the chart and the research it explains share ONE vertical axis
// with snap presets, so moving between "look at the price" and "read the evidence" is a
// keypress, never a scroll to somewhere the chart no longer exists. Heights are remembered
// per tab because Fundamentals small multiples need room Overview would only waste.

import { useRef, useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';
import { Rows2 } from 'lucide-react';
import {
  DRAWER_MAX_PERCENT,
  DRAWER_MIN_PERCENT,
  RESEARCH_TABS,
  clampDrawerSize,
  type DrawerSnap,
  type ResearchTab,
} from './tickerWorkspaceState';
import './financialResearch.css';

export function ResearchDrawer({
  tab,
  onTab,
  tabs,
  snap,
  onSnap,
  size,
  onResize,
  onCycleSnap,
  warnings,
  children,
}: {
  tab: ResearchTab;
  onTab: (tab: ResearchTab) => void;
  /** Tabs that can show something real for this asset — a fund has no issuer filings. */
  tabs: ResearchTab[];
  snap: DrawerSnap;
  onSnap: (snap: DrawerSnap) => void;
  size?: number;
  onResize: (size: number) => void;
  onCycleSnap: () => void;
  /** Per-tab problem counts. These must survive the collapsed drawer, or a workspace with a
   *  failed SEC pull and a healthy one look identical. */
  warnings: Partial<Record<ResearchTab, number>>;
  children: ReactNode;
}) {
  return (
    <section
      className="tw-drawer"
      data-snap={snap}
      data-custom-size={size != null && snap !== 'collapsed' ? 'true' : undefined}
      style={size != null && snap !== 'collapsed' ? { height: `${size}%` } : undefined}
      aria-label="Research"
    >
      {snap !== 'collapsed' && <DrawerResizeHandle size={size ?? (snap === 'full' ? 68 : 40)} onResize={onResize} />}
      <div className="tw-drawer__tabs" role="tablist">
        {RESEARCH_TABS.filter((entry) => tabs.includes(entry.id)).map((entry) => {
          const count = warnings[entry.id] ?? 0;
          return (
            <button
              key={entry.id}
              type="button"
              role="tab"
              className="tw-tab"
              aria-selected={tab === entry.id && snap !== 'collapsed'}
              onClick={() => {
                if (tab === entry.id && snap !== 'collapsed') onSnap('collapsed');
                else onTab(entry.id);
              }}
            >
              {entry.label}
              {count > 0 && <span className="tw-tab__badge" title={`${count} item${count === 1 ? '' : 's'} need attention`}>{count}</span>}
            </button>
          );
        })}
        <span style={{ flex: 1 }} />
        <button
          type="button"
          className="tw-iconbtn"
          onClick={onCycleSnap}
          title={`Drawer height: ${size != null ? 'custom' : snap} — press \\ to cycle`}
          aria-label="Cycle drawer height"
        >
          <Rows2 size={14} />
        </button>
      </div>
      {snap !== 'collapsed' && (
        <div className="tw-drawer__panel" role="tabpanel">{children}</div>
      )}
    </section>
  );
}

function DrawerResizeHandle({ size, onResize }: { size: number; onResize: (size: number) => void }) {
  const handleRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointerId: number; startY: number; startSize: number; frameHeight: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  const start = (event: PointerEvent<HTMLDivElement>) => {
    const frame = handleRef.current?.parentElement?.parentElement;
    if (!frame) return;
    drag.current = { pointerId: event.pointerId, startY: event.clientY, startSize: size, frameHeight: frame.clientHeight };
    event.currentTarget.setPointerCapture(event.pointerId);
    setDragging(true);
    event.preventDefault();
  };

  const move = (event: PointerEvent<HTMLDivElement>) => {
    const active = drag.current;
    if (!active || active.pointerId !== event.pointerId) return;
    const delta = ((active.startY - event.clientY) / active.frameHeight) * 100;
    onResize(clampDrawerSize(active.startSize + delta));
  };

  const finish = (event: PointerEvent<HTMLDivElement>) => {
    if (drag.current?.pointerId !== event.pointerId) return;
    drag.current = null;
    setDragging(false);
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
  };

  const keyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === 'ArrowUp') onResize(clampDrawerSize(size + 2));
    else if (event.key === 'ArrowDown') onResize(clampDrawerSize(size - 2));
    else if (event.key === 'Home') onResize(DRAWER_MIN_PERCENT);
    else if (event.key === 'End') onResize(DRAWER_MAX_PERCENT);
    else return;
    event.preventDefault();
  };

  return (
    <div
      ref={handleRef}
      className="tw-drawer__resize"
      data-dragging={dragging}
      role="separator"
      aria-label="Resize chart and research panels"
      aria-orientation="horizontal"
      aria-valuemin={DRAWER_MIN_PERCENT}
      aria-valuemax={DRAWER_MAX_PERCENT}
      aria-valuenow={Math.round(size)}
      aria-valuetext={`${Math.round(size)}% research panel`}
      tabIndex={0}
      onPointerDown={start}
      onPointerMove={move}
      onPointerUp={finish}
      onPointerCancel={finish}
      onKeyDown={keyDown}
    >
      <span />
    </div>
  );
}
