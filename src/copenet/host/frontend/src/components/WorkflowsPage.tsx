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
      <div className="shell-workbench-hero rounded-[24px] border border-shell-border px-6 py-5 shadow-shell">
        <div className="shell-workbench-grid relative">
          <div className="max-w-2xl">
            <div className="mb-2 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.24em] text-shell-accent">
              <Layers3 className="h-3 w-3" />
              workflows · workbench
            </div>
            <h1 className="font-display text-4xl leading-tight text-shell-text">
              Turn repeatable effort into living playbooks.
            </h1>
            <p className="mt-2 max-w-xl text-[13px] leading-relaxed text-shell-muted">
              Workflows are dedicated surfaces for the work you do over and over. Each one should feel like a
              purpose-built bench with a clear loop, not a chat window pretending to be a tool.
            </p>
          </div>

          <div className="shell-workbench-card self-end rounded-[20px] border border-shell-border px-4 py-4 shadow-shell">
            <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Workbench State</div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              {[
                { label: 'Live', value: '1' },
                { label: 'Drafting', value: '2' },
                { label: 'Direction', value: 'Bench-first' },
                { label: 'Focus', value: 'Meme Lab' },
              ].map((item) => (
                <div key={item.label} className="rounded-[16px] border border-shell-border bg-shell-panel-strong/60 px-3 py-3">
                  <div className="text-[10px] uppercase tracking-[0.16em] text-shell-muted">{item.label}</div>
                  <div className="mt-1 text-[1.1rem] font-semibold tracking-tight text-shell-text">{item.value}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <div className="grid items-start gap-3 xl:grid-cols-[minmax(0,1.34fr)_minmax(320px,0.66fr)]">
        <PlaybookCard
          featured
          live
          eyebrow="featured live · creative loop"
          title="Meme Lab"
          blurb="Ideate, rank, and arena-battle meme candidates for the Instagram pipeline. Topic in, survivors out, and keepers stay close enough to ship."
          icon={FlaskConical}
          stats={[
            { label: 'endpoint', value: '/memes/ideate' },
            { label: 'modes', value: 'stream · gallery · arena' },
            { label: 'loop', value: 'self-learning' },
            { label: 'outcome', value: 'keepers ready' },
          ]}
          onOpen={() => onOpen('meme-lab')}
        />

        <div className="space-y-3">
          <div className="shell-workbench-card rounded-[20px] border border-shell-border px-5 py-4 shadow-shell">
            <div className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.22em] text-shell-accent">
              <Sparkles className="h-3 w-3" />
              Launchpad
            </div>
            <p className="mt-3 text-[13px] leading-6 text-shell-muted">
              Workflows should feel like dedicated production surfaces. One live bench gets the spotlight;
              the rest stay clear about whether they are real, drafting, or directional.
            </p>
            <div className="mt-4 inline-flex items-center gap-1.5 font-mono text-[11px] uppercase tracking-[0.22em] text-shell-accent">
              active workbench
              <ArrowRight className="h-3.5 w-3.5" />
            </div>
          </div>

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
        </div>
      </div>

      <div className="grid items-start grid-cols-1 gap-3 md:grid-cols-2">
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

        <div className="shell-workbench-card rounded-[20px] border border-dashed border-shell-border px-5 py-5 shadow-shell">
          <div className="font-mono text-[10px] uppercase tracking-[0.22em] text-shell-accent">Bench philosophy</div>
          <div className="mt-2 font-display text-2xl text-shell-text">One live surface should feel inevitable.</div>
          <p className="mt-2 text-[13px] leading-6 text-shell-muted">
            The hub is here to route you into the real workbench quickly. Featured workflows earn space.
            Drafts stay visible, but calmer, until they deserve promotion.
          </p>
          <div className="mt-4 flex items-center gap-2 font-mono text-[11px] uppercase tracking-[0.22em] text-shell-muted">
            <span className="inline-flex items-center gap-1 rounded-md border border-shell-accent/30 bg-shell-accent-soft px-2 py-1 text-shell-accent">
              <Sparkles className="h-3 w-3" />
              1 live
            </span>
            <span className="inline-flex items-center gap-1 rounded-md border border-shell-border bg-shell-panel-strong/60 px-2 py-1">
              2 drafting
            </span>
          </div>
        </div>
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
  featured,
  live,
  eyebrow,
  title,
  blurb,
  icon: Icon,
  stats,
  onOpen,
}: {
  featured?: boolean;
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
      className={`shell-workbench-card group relative flex h-full flex-col overflow-hidden rounded-[20px] border bg-shell-panel p-5 text-left shadow-shell transition-all duration-200 ${
        featured ? 'shell-workbench-feature' : ''
      } ${
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
