import { createPortal } from 'react-dom';
import { X } from 'lucide-react';

interface MobileSheetProps {
  open: boolean;
  title: string;
  onClose: () => void;
  children: import('react').ReactNode;
  fullHeight?: boolean;
}

export function MobileSheet({ open, title, onClose, children, fullHeight = false }: MobileSheetProps) {
  if (!open || typeof document === 'undefined') return null;

  return createPortal(
    <div className="fixed inset-0 z-[70] lg:hidden">
      <button
        type="button"
        aria-label="Close sheet"
        onClick={onClose}
        className="absolute inset-0 bg-black/30 backdrop-blur-[2px]"
      />
      <div
        className={`absolute inset-x-0 bottom-0 flex max-h-[92svh] flex-col overflow-hidden rounded-t-[28px] border border-shell-border bg-shell-panel shadow-shell-xl ${
          fullHeight ? 'top-14' : 'min-h-[40svh]'
        }`}
      >
        <div className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-shell-border-strong" />
        <div className="flex items-center justify-between gap-3 border-b border-shell-border px-4 py-3">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em] text-shell-muted">{title}</div>
          <button
            type="button"
            onClick={onClose}
            className="inline-flex h-9 w-9 items-center justify-center rounded-full border border-shell-border bg-shell-bg text-shell-text"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">{children}</div>
      </div>
    </div>,
    document.body,
  );
}
