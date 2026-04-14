import { ArrowRight, LucideIcon } from 'lucide-react';

interface SectionCard {
  title: string;
  body: string;
  eyebrow?: string;
}

interface SectionPageProps {
  title: string;
  subtitle: string;
  accent: string;
  heroTitle: string;
  heroBody: string;
  icon: LucideIcon;
  cards: SectionCard[];
}

export function SectionPage({
  title,
  subtitle,
  accent,
  heroTitle,
  heroBody,
  icon: Icon,
  cards,
}: SectionPageProps) {
  return (
    <div className="space-y-6">
      <section className="rounded-[34px] border border-shell-border bg-shell-panel px-8 py-8 shadow-shell">
        <div className="max-w-3xl">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-shell-border bg-shell-bg px-4 py-2 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
            <Icon className={`h-3.5 w-3.5 ${accent}`} />
            {title}
          </div>
          <h1 className="font-display text-5xl leading-[1.02] tracking-tight text-shell-text">{heroTitle}</h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-shell-muted">{heroBody}</p>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <div key={card.title} className="rounded-[28px] border border-shell-border bg-shell-panel px-5 py-5 shadow-shell">
            {card.eyebrow && (
              <div className="mb-4 text-xs font-semibold uppercase tracking-[0.22em] text-shell-muted">
                {card.eyebrow}
              </div>
            )}
            <h2 className="text-lg font-semibold text-shell-text">{card.title}</h2>
            <p className="mt-3 text-sm leading-6 text-shell-muted">{card.body}</p>
            <div className="mt-5 inline-flex items-center gap-2 text-sm font-medium text-shell-text">
              <span>Coming into focus</span>
              <ArrowRight className="h-4 w-4 text-shell-muted" />
            </div>
          </div>
        ))}
      </section>

      <section className="rounded-[34px] border border-dashed border-shell-border bg-shell-panel px-8 py-10 text-center shadow-shell">
        <div className="mx-auto max-w-2xl">
          <h2 className="text-2xl font-semibold tracking-tight text-shell-text">{subtitle}</h2>
          <p className="mt-4 text-sm leading-7 text-shell-muted">
            This section is intentionally presentable before it is fully wired. The design is here to set the product direction first, then we can layer real data and behavior into it.
          </p>
        </div>
      </section>
    </div>
  );
}
