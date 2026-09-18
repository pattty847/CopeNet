import { useEffect, useId, useRef, type ReactNode } from 'react';
import { X } from 'lucide-react';

/** Native dialog supplies focus containment, Escape and an inert background. */
export function MonitoringSheet({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const close = () => {
    ref.current?.close();
    onClose();
  };
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.showModal();
    return () => {
      dialog?.close();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      className="mm-monitor-sheet"
      aria-labelledby={titleId}
      onClick={(event) => { if (event.target === event.currentTarget) close(); }}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <header>
        <h2 id={titleId}>{title}</h2>
        <button type="button" className="tw-iconbtn" onClick={close} aria-label={`Close ${title}`}>
          <X size={16} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
