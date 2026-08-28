import { useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';

export function MarketFloatingPopover({
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

  useEffect(() => {
    if (!open) return;
    const dismiss = (event: MouseEvent) => {
      if (!dismissOnOutside) return;
      const target = event.target as Node;
      if (!popoverRef.current?.contains(target) && !anchorRef.current?.contains(target)) onClose();
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('mousedown', dismiss);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', dismiss);
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
