import { GripVertical, ScanSearch } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import type { ReactElement } from 'react';
import { cn } from '../../lib/utils';
import { heightClassForHomeCard, HOME_CARD_DESCRIPTORS, type HomeCardId, type HomeCardLayoutItem } from './homeLayout';

interface HomeLayoutCardProps {
  item: HomeCardLayoutItem;
  customizing: boolean;
  isMobile: boolean;
  draggingId: HomeCardId | null;
  dropTargetId: HomeCardId | null;
  onDragStart: (id: HomeCardId) => void;
  onDragEnd: () => void;
  onDropOn: (id: HomeCardId) => void;
  onResize: (id: HomeCardId, axis: 'span' | 'height', direction: 'grow' | 'shrink') => void;
  children: ReactElement;
}

export function HomeLayoutCard({
  item,
  customizing,
  isMobile,
  draggingId,
  dropTargetId,
  onDragStart,
  onDragEnd,
  onDropOn,
  onResize,
  children,
}: HomeLayoutCardProps) {
  const descriptor = HOME_CARD_DESCRIPTORS[item.id];
  const [resizing, setResizing] = useState(false);
  const pointerState = useRef<{ startX: number; startY: number; pointerId: number } | null>(null);

  useEffect(() => {
    if (!resizing) return;
    const onPointerMove = () => {};
    const onPointerUp = (event: PointerEvent) => {
      const state = pointerState.current;
      if (!state || event.pointerId !== state.pointerId) return;
      const dx = event.clientX - state.startX;
      const dy = event.clientY - state.startY;
      const horizontal = Math.abs(dx) >= Math.abs(dy);
      if (horizontal && Math.abs(dx) >= 12) {
        onResize(item.id, 'span', dx > 0 ? 'grow' : 'shrink');
      } else if (!horizontal && Math.abs(dy) >= 12) {
        onResize(item.id, 'height', dy > 0 ? 'grow' : 'shrink');
      }
      pointerState.current = null;
      setResizing(false);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };
  }, [item.id, onResize, resizing]);

  const spanClass = isMobile
    ? 'col-span-1'
    : item.span === 12
      ? 'lg:col-span-12'
      : item.span === 8
        ? 'lg:col-span-8'
        : item.span === 6
          ? 'lg:col-span-6'
          : item.span === 4
            ? 'lg:col-span-4'
            : 'lg:col-span-12';

  return (
    <div
      data-home-card={item.id}
      draggable={customizing && !isMobile}
      onDragStart={(event) => {
        if (!customizing || isMobile) return;
        event.dataTransfer.effectAllowed = 'move';
        onDragStart(item.id);
      }}
      onDragEnd={onDragEnd}
      onDragOver={(event) => {
        if (!customizing || isMobile) return;
        event.preventDefault();
      }}
      onDragEnter={() => {
        if (!customizing || isMobile) return;
        onDropOn(item.id);
      }}
      onDrop={(event) => {
        if (!customizing || isMobile) return;
        event.preventDefault();
        onDropOn(item.id);
      }}
      className={cn(
        'relative min-w-0 transition-all duration-150',
        spanClass,
        heightClassForHomeCard(item.height),
        customizing && !isMobile && 'select-none',
        draggingId === item.id && 'opacity-55 scale-[0.99]',
        dropTargetId === item.id && draggingId !== item.id && 'translate-y-[-2px]',
      )}
    >
      {customizing && !isMobile && (
        <div className="pointer-events-none absolute inset-0 z-10 rounded-[28px] border border-shell-accent/30 bg-shell-accent/[0.03]" />
      )}
      <div className="relative h-full min-w-0">
        {customizing && !isMobile && (
          <div className="absolute right-3 top-3 z-20 flex items-center gap-1.5">
            <div
              className="flex h-8 cursor-grab items-center gap-1.5 rounded-full border border-shell-border bg-shell-panel/92 px-2.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-shell-muted shadow-shell backdrop-blur active:cursor-grabbing"
              title={`Drag ${descriptor.title}`}
            >
              <GripVertical className="h-3.5 w-3.5" />
              Move
            </div>
          </div>
        )}

        {children}

        {customizing && !isMobile && (
          <button
            type="button"
            aria-label={`Resize ${descriptor.title}`}
            title="Drag to resize. Horizontal changes width, vertical changes height."
            onPointerDown={(event) => {
              event.preventDefault();
              pointerState.current = {
                startX: event.clientX,
                startY: event.clientY,
                pointerId: event.pointerId,
              };
              setResizing(true);
            }}
            className={cn(
              'absolute bottom-3 right-3 z-20 inline-flex h-8 w-8 items-center justify-center rounded-full border border-shell-border bg-shell-panel/92 text-shell-muted shadow-shell backdrop-blur transition-colors hover:border-shell-accent/35 hover:text-shell-accent',
              resizing && 'border-shell-accent/45 text-shell-accent',
            )}
          >
            <ScanSearch className="h-3.5 w-3.5 rotate-90" />
          </button>
        )}
      </div>
    </div>
  );
}
