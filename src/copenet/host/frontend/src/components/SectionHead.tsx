import type { LucideIcon } from 'lucide-react';
import type { ReactNode } from 'react';

/** The utility pages' header: name, one caps line of context, and whatever acts on the
 *  whole page — the same grammar as the market bar.
 *
 *  It replaces the full-width marketing hero every one of these pages used to open with. A
 *  2.6rem serif headline and two sentences of prose telling the operator what their own
 *  workspace is for cost half a screen on every visit and said nothing on the second one. */
export function SectionHead({
  icon: Icon,
  title,
  context,
  children,
}: {
  icon?: LucideIcon;
  title: string;
  context?: string;
  children?: ReactNode;
}) {
  return (
    <header className="shell-section-head">
      {Icon && <Icon className="h-3.5 w-3.5 self-center text-shell-accent" />}
      <h1>{title}</h1>
      {context && <p>{context}</p>}
      <div className="shell-section-head__spacer" />
      {children}
    </header>
  );
}
