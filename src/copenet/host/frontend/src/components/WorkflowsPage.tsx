import { ArrowRight, FlaskConical, Layers3, Repeat2, ScrollText, Sparkles } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { MemeLab } from '../workflows/meme/MemeLab';

export function WorkflowsPage() {
  const route = useAppStore((state) => state.workflowsRoute);
  const setRoute = useAppStore((state) => state.setWorkflowsRoute);

  if (route === 'meme-lab') {
    return <MemeLab onExit={() => setRoute('hub')} />;
  }

  return <WorkflowsHub onOpen={setRoute} />;
}

function WorkflowsHub({ onOpen }: { onOpen: (route: 'meme-lab') => void }) {
  return (
    <div className="flex min-h-0 flex-col gap-5">
      {/* Hero */}
      <div className="relative overflow-hidden rounded-[24px] border border-shell-border bg-shell-panel px-6 py-5 shadow-shell">
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-shell-accent/15 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <div className="mb-2 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.24em] text-shell-accent">
              <Layers3 className="h-3 w-3" />
              workflows · v1
            </div>
            <h1 className="font-display text-4xl leading-tight text-shell-text">
              Turn repeatable effort into living playbooks.
            </h1>
            <p className="mt-2 text-[13px] leading-relaxed text-shell-muted">
              Workflows are dedicated surfaces for the work you do over and over. Each one is a purpose-built
              operator cockpit — not a chat window pretending to be a tool.
            </p>
          </div>
          <div className="flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-shell-muted">
            <span className="inline-flex items-center gap-1 rounded-md border border-shell-accent/30 bg-shell-accent-soft px-2 py-1 text-shell-accent">
              <Sparkles className="h-3 w-3" />
              1 live
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-shell-border bg-shell-panel-strong/60 px-2 py-1">
              3 drafting
            </span>
          </div>
        </div>
      </div>

      {/* Playbook grid */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        <PlaybookCard
          live
          eyebrow="creative · copeharderpls"
          title="Meme Lab"
          blurb="Ideate, rank, and arena-battle meme candidates for the Instagram pipeline. Topic in, survivors out."
          icon={FlaskConical}
          stats={[
            { label: 'endpoint', value: '/memes/ideate' },
            { label: 'modes', value: 'stream · gallery · arena' },
            { label: 'loop', value: 'self-learning' },
          ]}
          onOpen={() => onOpen('meme-lab')}
        />

        <PlaybookCard
          eyebrow="upcoming · synthesis"
          title="Prompt Forge"
          blurb="Turn a good chat session into a reusable prompt preset with grounded tool policy."
          icon={ScrollText}
          stats={[
            { label: 'status', value: 'drafting' },
            { label: 'source', value: 'agents session' },
          ]}
        />

        <PlaybookCard
          eyebrow="upcoming · scheduling"
          title="Recurring Runs"
          blurb="Cron-like scheduled runs with provider pinning and append-only transcripts."
          icon={Repeat2}
          stats={[
            { label: 'status', value: 'drafting' },
            { label: 'storage', value: 'transcripts' },
          ]}
        />
      </div>

      {/* Footer strip */}
      <div className="rounded-[18px] border border-dashed border-shell-border bg-shell-panel-strong/30 px-5 py-4 text-[12px] leading-relaxed text-shell-muted">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-shell-accent">note · </span>
        Meme Lab is the first playbook to graduate from mock to live endpoint. The rest are intentional
        placeholders — they describe the shape of workflows we want to build next, not vaporware.
      </div>
    </div>
  );
}

function PlaybookCard({
  live,
  eyebrow,
  title,
  blurb,
  icon: Icon,
  stats,
  onOpen,
}: {
  live?: boolean;
  eyebrow: string;
  title: string;
  blurb: string;
  icon: typeof FlaskConical;
  stats: { label: string; value: string }[];
  onOpen?: () => void;
}) {
  const interactive = Boolean(onOpen);
  return (
    <button
      type="button"
      onClick={onOpen}
      disabled={!interactive}
      className={`group relative flex h-full flex-col overflow-hidden rounded-[20px] border bg-shell-panel p-5 text-left shadow-shell transition-all duration-200 ${
        interactive
          ? 'border-shell-border hover:-translate-y-0.5 hover:border-shell-accent/40 hover:shadow-shell-hover'
          : 'border-shell-border/70 opacity-75'
      }`}
    >
      {live && (
        <span className="absolute right-4 top-4 inline-flex items-center gap-1 rounded-md border border-shell-success/40 bg-shell-success/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.22em] text-shell-success">
          <span className="pulse-live h-1.5 w-1.5 rounded-full bg-shell-success" />
          live
        </span>
      )}
      <div className="mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-shell-accent/30 bg-shell-accent-soft text-shell-accent">
        <Icon className="h-5 w-5" />
      </div>
      <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.22em] text-shell-muted">{eyebrow}</div>
      <div className="mb-2 font-display text-2xl text-shell-text">{title}</div>
      <p className="mb-4 flex-1 text-[12.5px] leading-relaxed text-shell-muted">{blurb}</p>

      <dl className="mb-4 grid grid-cols-1 gap-1.5">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="flex items-center justify-between gap-3 border-t border-shell-border/60 pt-1.5 font-mono text-[11px] first:border-t-0 first:pt-0"
          >
            <dt className="text-[10px] uppercase tracking-[0.22em] text-shell-muted">{stat.label}</dt>
            <dd className="truncate tabular-nums text-shell-text/90">{stat.value}</dd>
          </div>
        ))}
      </dl>

      {interactive && (
        <div className="inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.22em] text-shell-accent transition-transform group-hover:translate-x-0.5">
          open workbench
          <ArrowRight className="h-3.5 w-3.5" />
        </div>
      )}
    </button>
  );
}
