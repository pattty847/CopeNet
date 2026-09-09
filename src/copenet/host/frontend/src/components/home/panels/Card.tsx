import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

/** Every Home panel is one card about one subject: a caps title, an optional action in the
 *  head, and a body. Shared so the eight panels cannot drift apart one hairline at a time. */
export function Card({
  title,
  icon: Icon,
  span,
  head,
  children,
  className = '',
}: {
  title?: string;
  icon?: LucideIcon;
  span: 3 | 4 | 5 | 6 | 7 | 8 | 12;
  /** Anything that acts on the whole panel — a link out, a tab strip, a status. */
  head?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`hd-card hd-span-${span} ${className}`}>
      {title && (
        <header className="hd-card__head">
          {Icon && <Icon size={11} />}
          <b>{title}</b>
          {head}
        </header>
      )}
      <div className="hd-card__body">{children}</div>
    </section>
  );
}

export function CardLink({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button type="button" className="hd-link" onClick={onClick}>
      {label} →
    </button>
  );
}
