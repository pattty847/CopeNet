import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';

/** Portalled to `document.body` and positioned with `fixed`, on purpose: an anchor that
 *  lives in the persistent app chrome (a toolbar, the header) sits in a flex sibling of the
 *  scrollable content area, and that sibling relationship put popovers rendered in place
 *  behind the content — a real z-index had no effect because the two were never in the same
 *  paint layer. Escaping to body sidesteps it instead of chasing the exact stacking cause. */
export function FloatingPopover({
  anchorRef,
  open,
  onClose,
  className,
  width,
  dismissOnOutside = true,
  children,
}: {
  anchorRef: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  className?: string;
  width: number;
  dismissOnOutside?: boolean;
  children: ReactNode;
}) {
  const popoverRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ top: 72, left: 12 });

  useLayoutEffect(() => {
    if (!open) return;
    const update = () => {
      const anchor = anchorRef.current?.getBoundingClientRect();
      const popoverHeight = popoverRef.current?.offsetHeight ?? 280;
      if (!anchor) return;
      const safeWidth = Math.min(width, window.innerWidth - 24);
      const left = Math.min(Math.max(12, anchor.right - safeWidth), window.innerWidth - safeWidth - 12);
      const below = anchor.bottom + 8;
      const top = below + popoverHeight <= window.innerHeight - 12
        ? below
        : Math.max(12, anchor.top - popoverHeight - 8);
      setPosition({ top, left });
    };
    update();
    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [anchorRef, open, width]);

  // `pointerdown`, in the capture phase, rather than `mousedown`.
  //
  // A tap on the Lightweight Charts canvas produced no dismissal on a phone: the library
  // handles the touch itself and calls `preventDefault`, which suppresses the synthesized
  // mouse events, so `mousedown` never reached this listener. The chart menus therefore
  // stayed open over the chart — and because opening a second menu also relies on this
  // listener to close the first, every menu could be open at once. `pointerdown` fires for
  // touch, pen and mouse alike, and capture means nothing downstream can stop it.
  useEffect(() => {
    if (!open) return;
    const dismiss = (event: Event) => {
      if (!dismissOnOutside) return;
      const target = event.target as Node;
      if (!popoverRef.current?.contains(target) && !anchorRef.current?.contains(target)) onClose();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('pointerdown', dismiss, true);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', dismiss, true);
      document.removeEventListener('keydown', escape);
    };
  }, [anchorRef, dismissOnOutside, onClose, open]);

  if (!open) return null;
  return createPortal(
    <div
      ref={popoverRef}
      className={className}
      style={{ position: 'fixed', top: position.top, left: position.left, width: Math.min(width, window.innerWidth - 24), zIndex: 70 }}
    >
      {children}
    </div>,
    document.body,
  );
}
