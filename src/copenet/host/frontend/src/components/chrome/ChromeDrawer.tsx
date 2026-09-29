import { useEffect, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { X, type LucideIcon } from 'lucide-react';

/** The right-hand slide-over for app-chrome panels (Settings, Alerts, Notebook). Portalled
 *  for the same stacking reason as FloatingPopover; full width on a phone. */
export function ChromeDrawer({
  title,
  eyebrow,
  icon: Icon,
  onClose,
  children,
}: {
  title: string;
  eyebrow: string;
  icon: LucideIcon;
  onClose: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return createPortal(
    <div className="fixed inset-0 z-[80] flex" role="dialog" aria-modal="true" aria-label={title}>
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative ml-auto flex h-full w-full max-w-[560px] flex-col border-l border-shell-border bg-shell-canvas shadow-shell-xl animate-slide-in-right">
        <div className="flex items-center gap-2.5 border-b border-shell-border px-4 py-3 pt-[calc(env(safe-area-inset-top)+0.75rem)]">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-shell-accent-soft text-shell-accent">
            <Icon className="h-3.5 w-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[9.5px] font-semibold uppercase tracking-[0.16em] text-shell-muted">{eyebrow}</div>
            <div className="mt-0.5 truncate text-[14px] font-semibold text-shell-text">{title}</div>
          </div>
          <button
            type="button"
            onClick={onClose}
            title="Close (Esc)"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-shell-muted transition-colors hover:bg-shell-panel hover:text-shell-text"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4 pb-[calc(env(safe-area-inset-bottom)+1rem)]">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

export function ChromeSection({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="mb-6 last:mb-0">
      <h3 className="text-[10.5px] font-semibold uppercase tracking-[0.14em] text-shell-muted">{title}</h3>
      {hint && <p className="mt-1 text-[12px] leading-relaxed text-shell-muted">{hint}</p>}
      <div className="mt-2.5">{children}</div>
    </section>
  );
}
