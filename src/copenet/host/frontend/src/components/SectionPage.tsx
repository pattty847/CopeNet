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
    <div className="animate-fade-in-up space-y-3">
      {/* Hero */}
      <section className="rounded-[24px] border border-shell-border bg-shell-panel px-7 py-6 shadow-shell">
        <div className="max-w-3xl">
          <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-shell-accent/15 bg-shell-accent-soft px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-accent">
            <Icon className="h-3 w-3" />
            {title}
          </div>
          <h1 className="font-display text-[2.6rem] leading-[1.02] tracking-tight text-shell-text">{heroTitle}</h1>
          <p className="mt-3 max-w-xl text-[14px] leading-6 text-shell-muted">{heroBody}</p>
        </div>
      </section>

      {/* Cards */}
      <section className="stagger-children grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
        {cards.map((card) => (
          <div key={card.title} className="lift-sm rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
            {card.eyebrow && (
              <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-accent">
                {card.eyebrow}
              </div>
            )}
            <h2 className="text-[15px] font-semibold text-shell-text">{card.title}</h2>
            <p className="mt-2 text-[13px] leading-5 text-shell-muted">{card.body}</p>
            <div className="mt-4 inline-flex items-center gap-1.5 text-[12px] font-medium text-shell-muted transition-colors duration-150 hover:text-shell-accent">
              <span>Coming into focus</span>
              <ArrowRight className="h-3 w-3" />
            </div>
          </div>
        ))}
      </section>

      {/* Footer */}
      <section className="rounded-[24px] border border-dashed border-shell-border bg-shell-panel px-7 py-8 text-center">
        <div className="mx-auto max-w-xl">
          <h2 className="font-display text-2xl tracking-tight text-shell-text">{subtitle}</h2>
          <p className="mt-3 text-[13px] leading-6 text-shell-muted">
            This section is intentionally presentable before it is fully wired. The design is here to set the product direction first, then we can layer real data and behavior into it.
          </p>
        </div>
      </section>
    </div>
  );
}
