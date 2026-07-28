// Draggable, resizable panel grid for the Market Monitor.
//
// Layout is the operator's, not ours: positions and sizes persist per device and survive reloads.
// Two deliberate constraints —
//   1. drag/resize only in Arrange mode, so a click on a panel button can never become a drag
//   2. mobile renders the panels stacked, never gridded — a 12-column grid on a phone is a worse
//      layout than the linear one, and hand-tuned desktop positions do not translate
// Unknown ids in a stored layout are dropped and new panels fall in at their default slot, so
// adding or removing a panel never strands someone on a broken saved layout.

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import { GridLayout, useContainerWidth, type Layout, type LayoutItem } from 'react-grid-layout';

import 'react-grid-layout/css/styles.css';

import { useIsMobile } from '../../lib/responsive';
import { MM } from './marketUi';

export const GRID_COLUMNS = 12;
export const GRID_ROW_HEIGHT = 34;
const GRID_MARGIN: [number, number] = [16, 16];
const DRAG_HANDLE_CLASS = 'market-panel-drag-handle';

export interface MarketGridPanel {
  id: string;
  /** Grid slot in a 12-column grid. `h` is in row units (see GRID_ROW_HEIGHT). */
  layout: { x: number; y: number; w: number; h: number; minW?: number; minH?: number };
  node: ReactNode;
}

function readStoredLayout(storageKey: string): LayoutItem[] | null {
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as LayoutItem[]) : null;
  } catch {
    return null; // private mode, or a layout written by an older shape
  }
}

/** Stored positions win for panels that still exist; everything else falls back to its default. */
function mergeLayout(panels: MarketGridPanel[], stored: LayoutItem[] | null): Layout {
  const byId = new Map((stored ?? []).map((item) => [item.i, item]));
  return panels.map((panel) => {
    const saved = byId.get(panel.id);
    const base = { i: panel.id, minW: panel.layout.minW ?? 3, minH: panel.layout.minH ?? 4 };
    if (!saved) return { ...base, x: panel.layout.x, y: panel.layout.y, w: panel.layout.w, h: panel.layout.h };
    return { ...base, x: saved.x, y: saved.y, w: saved.w, h: saved.h };
  });
}

export function MarketGrid({ panels, storageKey }: { panels: MarketGridPanel[]; storageKey: string }) {
  const isMobile = useIsMobile();
  const { width, containerRef } = useContainerWidth();
  const [arranging, setArranging] = useState(false);
  const [stored, setStored] = useState<LayoutItem[] | null>(() => readStoredLayout(storageKey));

  const layout = useMemo(() => mergeLayout(panels, stored), [panels, stored]);

  const persist = useCallback(
    (next: Layout) => {
      const trimmed = next.map((item) => ({ i: item.i, x: item.x, y: item.y, w: item.w, h: item.h }));
      setStored(trimmed as LayoutItem[]);
      try {
        localStorage.setItem(storageKey, JSON.stringify(trimmed));
      } catch {
        /* private mode — the layout still applies for this session */
      }
    },
    [storageKey],
  );

  const reset = useCallback(() => {
    setStored(null);
    try {
      localStorage.removeItem(storageKey);
    } catch {
      /* nothing to clear */
    }
  }, [storageKey]);

  // Arrange mode is a desktop affordance; leaving it on while the window shrinks would strand
  // the toggle in a layout that cannot be dragged.
  useEffect(() => {
    if (isMobile) setArranging(false);
  }, [isMobile]);

  if (isMobile) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {panels.map((panel) => (
          <div key={panel.id}>{panel.node}</div>
        ))}
      </div>
    );
  }

  return (
    <div>
      <style>{`
        .${DRAG_HANDLE_CLASS} { cursor: default; }
        .market-grid-arranging .${DRAG_HANDLE_CLASS} { cursor: grab; }
        .market-grid-arranging .${DRAG_HANDLE_CLASS}:active { cursor: grabbing; }
        .market-grid-arranging .react-grid-item > * { outline: 1px dashed rgba(251,148,35,.35); outline-offset: 2px; border-radius: 14px; }
        .react-grid-item > .react-resizable-handle { opacity: 0; transition: opacity .15s; }
        .market-grid-arranging .react-grid-item > .react-resizable-handle { opacity: .85; }
        .react-grid-item.react-grid-placeholder { background: ${MM.accent}; opacity: .14; border-radius: 14px; }
        .react-grid-item > * { height: 100%; overflow: auto; }
      `}</style>

      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        {arranging && (
          <>
            <span style={{ fontSize: 10.5, color: MM.dim, fontStyle: 'italic', marginRight: 'auto' }}>
              Drag a panel by its header; drag the bottom-right corner to resize. Saved on this device.
            </span>
            <button
              onClick={reset}
              style={{ cursor: 'pointer', border: `1px solid ${MM.border}`, background: 'transparent', color: MM.muted, borderRadius: 8, padding: '5px 10px', font: '600 9px Inter', letterSpacing: '.08em', textTransform: 'uppercase' }}
            >
              ↺ Reset
            </button>
          </>
        )}
        <button
          onClick={() => setArranging((value) => !value)}
          style={{
            cursor: 'pointer',
            border: `1px solid ${arranging ? MM.borderHi : MM.border}`,
            background: arranging ? MM.accentSoft : 'transparent',
            color: arranging ? MM.accent : MM.muted,
            borderRadius: 8,
            padding: '5px 10px',
            font: '600 9px Inter',
            letterSpacing: '.08em',
            textTransform: 'uppercase',
          }}
        >
          {arranging ? '✓ Done' : '⌗ Arrange'}
        </button>
      </div>

      <div ref={containerRef} className={arranging ? 'market-grid-arranging' : undefined}>
        <GridLayout
          width={width}
          layout={layout}
          gridConfig={{ cols: GRID_COLUMNS, rowHeight: GRID_ROW_HEIGHT, margin: GRID_MARGIN, containerPadding: [0, 0] }}
          dragConfig={{ enabled: arranging, handle: `.${DRAG_HANDLE_CLASS}`, cancel: 'button, input, select, textarea, a' }}
          resizeConfig={{ enabled: arranging }}
          // Persist on the gesture, not on onLayoutChange: the latter also fires on mount and on
          // container resize, which would write a layout the operator never chose.
          onDragStop={(next) => persist(next)}
          onResizeStop={(next) => persist(next)}
        >
          {panels.map((panel) => (
            <div key={panel.id}>{panel.node}</div>
          ))}
        </GridLayout>
      </div>
    </div>
  );
}

/** Panels opt into dragging by putting this class on their header. */
export const dragHandleClass = DRAG_HANDLE_CLASS;
