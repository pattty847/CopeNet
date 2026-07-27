import { Activity, AlertTriangle, ArrowRight, CheckCircle2, GitBranch, PlayCircle, Radio } from 'lucide-react';
import type { MissionControlItem, MissionControlLane } from '../../lib/missionControl';

interface MissionControlPanelProps {
  items: MissionControlItem[];
  loading: boolean;
  onOpenSession: (item: MissionControlItem) => void;
  onOpenObservability: (item: MissionControlItem) => void;
  onPromoteWorkflow: (item: MissionControlItem) => void;
}

const LANE_META: Record<
  MissionControlLane,
  {
    label: string;
    hint: string;
    icon: typeof AlertTriangle;
  }
> = {
  needs_attention: {
    label: 'Needs Attention',
    hint: 'Approvals, failed runs, and active work.',
    icon: AlertTriangle,
  },
  recently_useful: {
    label: 'Recently Useful',
    hint: 'Runs that produced tool output or artifacts.',
    icon: CheckCircle2,
  },
  ready_to_continue: {
    label: 'Ready To Continue',
    hint: 'Stale sessions with a useful next step.',
    icon: PlayCircle,
  },
  promote_to_workflow: {
    label: 'Promote To Workflow',
    hint: 'Repeatable work that deserves a bench.',
    icon: GitBranch,
  },
};

const LANES: MissionControlLane[] = [
  'needs_attention',
  'recently_useful',
  'ready_to_continue',
  'promote_to_workflow',
];

function actionLabel(item: MissionControlItem): string {
  if (item.lane === 'promote_to_workflow') return 'Open workflow';
  if (item.kind === 'failed_run' || item.kind === 'useful_run') return 'Open run';
  return 'Open session';
}

function actionHandler(
  item: MissionControlItem,
  onOpenSession: (item: MissionControlItem) => void,
  onOpenObservability: (item: MissionControlItem) => void,
  onPromoteWorkflow: (item: MissionControlItem) => void,
) {
  if (item.lane === 'promote_to_workflow') return () => onPromoteWorkflow(item);
  if (item.kind === 'failed_run' || item.kind === 'useful_run') return () => onOpenObservability(item);
  return () => onOpenSession(item);
}

function MissionItem({
  item,
  onOpenSession,
  onOpenObservability,
  onPromoteWorkflow,
}: {
  item: MissionControlItem;
  onOpenSession: (item: MissionControlItem) => void;
  onOpenObservability: (item: MissionControlItem) => void;
  onPromoteWorkflow: (item: MissionControlItem) => void;
}) {
  return (
    <article className="group min-w-0 max-w-full overflow-hidden border-t border-shell-border/70 py-3 first:border-t-0 first:pt-0">
      <div className="flex min-w-0 flex-col items-start gap-2 sm:flex-row sm:justify-between sm:gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-start gap-2">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-shell-accent" />
            <h4
              className="min-w-0 break-words text-[13px] font-semibold leading-5 text-shell-text [overflow-wrap:anywhere]"
              title={item.title}
            >
              {item.title}
            </h4>
          </div>
          <p
            className="mt-1 line-clamp-2 min-w-0 break-words text-[12px] leading-5 text-shell-muted [overflow-wrap:anywhere]"
            title={item.detail}
          >
            {item.detail}
          </p>
        </div>
        <button
          type="button"
          onClick={actionHandler(item, onOpenSession, onOpenObservability, onPromoteWorkflow)}
          className="inline-flex h-8 shrink-0 items-center gap-1.5 self-start rounded-lg border border-shell-border bg-shell-panel-strong px-2.5 text-[11px] font-medium text-shell-text transition-colors hover:border-shell-accent/40 hover:text-shell-accent"
        >
          {actionLabel(item)}
          <ArrowRight className="h-3 w-3" />
        </button>
      </div>
      <div className="mt-2 flex min-w-0 max-w-full flex-wrap items-start gap-1.5 font-mono text-[10px] text-shell-muted">
        <span className="max-w-full break-words rounded-md border border-shell-border bg-shell-bg px-1.5 py-0.5 [overflow-wrap:anywhere]">
          {item.source}
        </span>
        <span className="max-w-full break-words rounded-md border border-shell-border bg-shell-bg px-1.5 py-0.5 [overflow-wrap:anywhere]">
          {item.provider}
        </span>
        {item.model ? (
          <span className="max-w-full break-words rounded-md border border-shell-border bg-shell-bg px-1.5 py-0.5 [overflow-wrap:anywhere] sm:max-w-[11rem]">
            {item.model}
          </span>
        ) : null}
        <span className="max-w-full break-words rounded-md border border-shell-border bg-shell-bg px-1.5 py-0.5 [overflow-wrap:anywhere]">
          {item.meta}
        </span>
      </div>
    </article>
  );
}

function Lane({
  lane,
  items,
  loading,
  onOpenSession,
  onOpenObservability,
  onPromoteWorkflow,
}: {
  lane: MissionControlLane;
  items: MissionControlItem[];
  loading: boolean;
  onOpenSession: (item: MissionControlItem) => void;
  onOpenObservability: (item: MissionControlItem) => void;
  onPromoteWorkflow: (item: MissionControlItem) => void;
}) {
  const meta = LANE_META[lane];
  const Icon = meta.icon;

  return (
    <section className="min-h-[15rem] min-w-0 max-w-full overflow-hidden rounded-[18px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell">
      <header className="mb-3 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Icon className="h-3.5 w-3.5 shrink-0 text-shell-accent" />
            <h3 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-shell-text">{meta.label}</h3>
          </div>
          <p className="mt-1 text-[11px] leading-4 text-shell-muted">{meta.hint}</p>
        </div>
        <span className="rounded-md border border-shell-border bg-shell-bg px-1.5 py-0.5 font-mono text-[10px] text-shell-muted">
          {items.length}
        </span>
      </header>

      {items.length > 0 ? (
        <div className="min-w-0">
          {items.slice(0, 3).map((item) => (
            <MissionItem
              key={item.id}
              item={item}
              onOpenSession={onOpenSession}
              onOpenObservability={onOpenObservability}
              onPromoteWorkflow={onPromoteWorkflow}
            />
          ))}
        </div>
      ) : (
        <div className="flex min-h-[9.5rem] flex-col justify-center rounded-[14px] border border-dashed border-shell-border bg-shell-bg px-3 py-4 text-[12px] leading-5 text-shell-muted">
          {loading ? 'Scanning sessions and recent runs…' : 'No urgent work in this lane.'}
        </div>
      )}
    </section>
  );
}

export function MissionControlPanel({
  items,
  loading,
  onOpenSession,
  onOpenObservability,
  onPromoteWorkflow,
}: MissionControlPanelProps) {
  const grouped = Object.fromEntries(LANES.map((lane) => [lane, items.filter((item) => item.lane === lane)])) as Record<
    MissionControlLane,
    MissionControlItem[]
  >;
  const hasItems = items.length > 0;

  return (
    <section className="min-w-0 max-w-full space-y-3 overflow-hidden" aria-label="Mission Control">
      <div className="flex flex-wrap items-end justify-between gap-3 px-1">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
            <Radio className="h-3 w-3" />
            Mission Control
          </div>
          <h2 className="mt-1 font-display text-2xl tracking-tight text-shell-text">Run Radar</h2>
          <p className="mt-1 max-w-2xl text-[12px] leading-5 text-shell-muted">
            The next useful places to look across sessions, runs, approvals, and repeatable work.
          </p>
        </div>
        <div className="inline-flex items-center gap-1.5 rounded-xl border border-shell-border bg-shell-panel px-3 py-2 font-mono text-[11px] text-shell-muted shadow-shell">
          <Activity className="h-3 w-3 text-shell-accent" />
          {loading ? 'scanning' : `${items.length} signal${items.length === 1 ? '' : 's'}`}
        </div>
      </div>

      {!hasItems && !loading ? (
        <div className="rounded-[18px] border border-dashed border-shell-border bg-shell-panel px-4 py-5 text-[13px] text-shell-muted shadow-shell">
          <span className="font-medium text-shell-text">No urgent work.</span> Recent sessions and runnable suggestions will appear here as CopeNet builds up run history.
        </div>
      ) : null}

      <div className="grid min-w-0 max-w-full gap-3 md:grid-cols-2 xl:grid-cols-4">
        {LANES.map((lane) => (
          <Lane
            key={lane}
            lane={lane}
            items={grouped[lane]}
            loading={loading}
            onOpenSession={onOpenSession}
            onOpenObservability={onOpenObservability}
            onPromoteWorkflow={onPromoteWorkflow}
          />
        ))}
      </div>
    </section>
  );
}
