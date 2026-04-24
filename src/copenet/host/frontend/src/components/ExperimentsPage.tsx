import { useEffect, useMemo, useState } from 'react';
import {
  Activity,
  ArrowRight,
  CheckCircle2,
  FlaskConical,
  GitCompareArrows,
  LoaderCircle,
  Plus,
  Swords,
  Timer,
  Wrench,
  XCircle,
  Zap,
} from 'lucide-react';
import { wsClient } from '../lib/wsClient';
import type { SessionRunRecord } from '../types/backend';
import { useAppStore } from '../store/useAppStore';

interface MatrixCell {
  runId: string;
  provider: string;
  model: string;
  status: SessionRunRecord['status'];
  durationMs: number | null;
  toolSteps: number;
  userMessage: string;
  startedAt: string;
}

interface ProviderModelRow {
  provider: string;
  models: {
    model: string;
    runs: MatrixCell[];
  }[];
}

function durationMs(run: SessionRunRecord): number | null {
  if (!run.startedAt || !run.completedAt) return null;
  const start = new Date(run.startedAt).getTime();
  const end = new Date(run.completedAt).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return Math.max(0, end - start);
}

function fmtMs(ms: number | null): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function fmtRelative(ts: string): string {
  const t = new Date(ts).getTime();
  if (!Number.isFinite(t)) return '—';
  const secs = Math.max(1, Math.round((Date.now() - t) / 1000));
  if (secs < 60) return `${secs}s ago`;
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

function statusTone(status: SessionRunRecord['status']) {
  switch (status) {
    case 'completed':
      return 'border-shell-success/30 bg-shell-success/10 text-shell-success';
    case 'error':
    case 'failed':
      return 'border-shell-error/30 bg-shell-error/10 text-shell-error';
    case 'running':
    case 'in_progress':
      return 'border-shell-accent/30 bg-shell-accent-soft text-shell-accent';
    default:
      return 'border-shell-border bg-shell-panel-strong/60 text-shell-muted';
  }
}

function StatusIcon({ status }: { status: SessionRunRecord['status'] }) {
  if (status === 'completed') return <CheckCircle2 className="h-3 w-3" />;
  if (status === 'error' || status === 'failed') return <XCircle className="h-3 w-3" />;
  if (status === 'running' || status === 'in_progress')
    return <LoaderCircle className="h-3 w-3 animate-spin" />;
  return <Activity className="h-3 w-3" />;
}

export function ExperimentsPage() {
  const sessions = useAppStore((state) => state.sessions);
  const [runs, setRuns] = useState<SessionRunRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = async () => {
    setLoading(true);
    setError(null);
    try {
      const active = sessions.filter((s) => !s.archived).slice(0, 12);
      const results = await Promise.all(
        active.map(async (session) => {
          try {
            return await wsClient.listSessionRuns(session.key, 25);
          } catch {
            return [] as SessionRunRecord[];
          }
        }),
      );
      const flat = results.flat();
      flat.sort((a, b) => (b.startedAt || '').localeCompare(a.startedAt || ''));
      setRuns(flat);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runs.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessions.length]);

  const matrix = useMemo<ProviderModelRow[]>(() => {
    const byProvider = new Map<string, Map<string, MatrixCell[]>>();
    for (const run of runs) {
      const provider = run.provider || 'unknown';
      const model = run.model || 'default';
      if (!byProvider.has(provider)) byProvider.set(provider, new Map());
      const inner = byProvider.get(provider)!;
      if (!inner.has(model)) inner.set(model, []);
      inner.get(model)!.push({
        runId: run.runId,
        provider,
        model,
        status: run.status,
        durationMs: durationMs(run),
        toolSteps: Array.isArray(run.toolSteps) ? run.toolSteps.length : 0,
        userMessage: run.userMessage || '',
        startedAt: run.startedAt || '',
      });
    }
    return [...byProvider.entries()]
      .map(([provider, models]) => ({
        provider,
        models: [...models.entries()].map(([model, runList]) => ({ model, runs: runList })),
      }))
      .sort((a, b) => a.provider.localeCompare(b.provider));
  }, [runs]);

  const stats = useMemo(() => {
    const total = runs.length;
    const done = runs.filter((r) => r.status === 'completed').length;
    const err = runs.filter((r) => r.status === 'error' || r.status === 'failed').length;
    const withTools = runs.filter((r) => Array.isArray(r.toolSteps) && r.toolSteps.length > 0).length;
    const durations = runs.map(durationMs).filter((x): x is number => x != null);
    const avg =
      durations.length > 0 ? durations.reduce((a, b) => a + b, 0) / durations.length : null;
    const providers = new Set(runs.map((r) => r.provider || 'unknown')).size;
    const models = new Set(runs.map((r) => `${r.provider}/${r.model}`)).size;
    return { total, done, err, withTools, avg, providers, models };
  }, [runs]);

  return (
    <div className="flex min-h-0 flex-col gap-5">
      {/* Hero */}
      <div className="shell-page-utility-hero relative overflow-hidden rounded-[24px] border border-shell-border bg-shell-panel px-6 py-5 shadow-shell">
        <div className="pointer-events-none absolute -right-16 -top-16 h-64 w-64 rounded-full bg-shell-accent/15 blur-3xl" />
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <div className="mb-2 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.24em] text-shell-accent">
              <FlaskConical className="h-3 w-3" />
              experiments · matrix
            </div>
            <h1 className="font-display text-4xl leading-tight text-shell-text">
              Run the same job across models. Watch what changes.
            </h1>
            <p className="mt-2 text-[13px] leading-relaxed text-shell-muted">
              A live provider × model matrix of every run touching CopeNet. Hover a cell to see the
              actual call — the data is already in sessions, this surface just makes it legible.
            </p>
          </div>
          <button
            type="button"
            onClick={() => void loadAll()}
            disabled={loading}
            className="focus-ring inline-flex items-center gap-2 rounded-xl border border-shell-accent/30 bg-shell-accent-soft px-3 py-2 font-mono text-[11px] uppercase tracking-[0.22em] text-shell-accent transition-all hover:bg-shell-accent/20 disabled:opacity-50"
          >
            {loading ? (
              <LoaderCircle className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Plus className="h-3.5 w-3.5" />
            )}
            refresh
          </button>
        </div>
      </div>

      {/* KPI tiles */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Kpi
          label="runs indexed"
          value={stats.total}
          sub={`${stats.done} ok · ${stats.err} err`}
          icon={Activity}
        />
        <Kpi
          label="avg duration"
          value={fmtMs(stats.avg)}
          sub="across sampled runs"
          icon={Timer}
          mono
        />
        <Kpi
          label="tool-loop runs"
          value={stats.withTools}
          sub={stats.total > 0 ? `${Math.round((stats.withTools / stats.total) * 100)}%` : '—'}
          icon={Wrench}
        />
        <Kpi
          label="matrix coverage"
          value={`${stats.providers}×${stats.models}`}
          sub="providers × models"
          icon={GitCompareArrows}
          mono
        />
      </div>

      {/* Matrix */}
      <div className="shell-page-utility-tile rounded-[20px] border border-shell-border bg-shell-panel shadow-shell">
        <div className="flex items-center justify-between border-b border-shell-border px-4 py-3">
          <div>
            <div className="font-display text-lg tracking-tight text-shell-text">
              Provider × model matrix
            </div>
            <div className="font-mono text-[11px] text-shell-muted">
              each cell is a recent run; click to inspect coming soon
            </div>
          </div>
          <div className="hidden items-center gap-3 font-mono text-[10px] uppercase tracking-[0.22em] text-shell-muted md:flex">
            <LegendDot tone="success" label="ok" />
            <LegendDot tone="error" label="err" />
            <LegendDot tone="live" label="live" />
          </div>
        </div>

        {error && (
          <div className="m-4 rounded-lg border border-shell-error/40 bg-shell-error/5 p-3 text-[12px] text-shell-error">
            {error}
          </div>
        )}

        {matrix.length === 0 ? (
          <div className="px-4 py-16 text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-dashed border-shell-border bg-shell-panel-strong/40 text-shell-muted">
              <Swords className="h-5 w-5" />
            </div>
            <div className="font-display text-lg text-shell-text">No runs to compare yet</div>
            <div className="mx-auto mt-1 max-w-md font-mono text-[11px] text-shell-muted">
              Send a message in Agents, then return — this matrix builds itself from real sessions.
            </div>
          </div>
        ) : (
          <div className="divide-y divide-shell-border/60">
            {matrix.map((row) => (
              <div key={row.provider} className="px-4 py-3">
                <div className="mb-2 flex items-center gap-2">
                  <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-shell-accent">
                    {row.provider}
                  </span>
                  <span className="font-mono text-[10px] text-shell-muted">
                    · {row.models.length} model{row.models.length === 1 ? '' : 's'}
                  </span>
                </div>
                <div className="space-y-2">
                  {row.models.map((m) => (
                    <ModelRow key={`${row.provider}/${m.model}`} model={m.model} runs={m.runs} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Future probe shelf */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        <FutureCard
          icon={Swords}
          eyebrow="next · probe"
          title="Prompt Face-Off"
          body="Send one prompt to every connected provider/model in parallel and diff the outputs side-by-side."
        />
        <FutureCard
          icon={Wrench}
          eyebrow="next · probe"
          title="Tool Use Compliance"
          body="Script a task that requires a specific tool call. Measure which runtimes follow the instruction versus drift."
        />
        <FutureCard
          icon={Zap}
          eyebrow="next · probe"
          title="Latency Leaderboard"
          body="Track time-to-first-token and tool-step durations per model so you can pick the right runtime for the job."
        />
      </div>
    </div>
  );
}

function ModelRow({ model, runs }: { model: string; runs: MatrixCell[] }) {
  const ordered = [...runs].sort((a, b) => (b.startedAt || '').localeCompare(a.startedAt || ''));
  const cap = 32;
  const visible = ordered.slice(0, cap);
  return (
    <div className="grid grid-cols-[minmax(0,220px)_1fr] items-center gap-3">
      <div className="truncate font-mono text-[12px] text-shell-text/90" title={model}>
        {model}
      </div>
      <div className="flex flex-wrap gap-1">
        {visible.map((run) => (
          <RunCell key={run.runId} cell={run} />
        ))}
        {ordered.length > cap && (
          <span className="inline-flex items-center rounded-md border border-shell-border bg-shell-panel-strong/60 px-1.5 py-0.5 font-mono text-[10px] text-shell-muted">
            +{ordered.length - cap}
          </span>
        )}
        <span className="ml-1 inline-flex items-center font-mono text-[10px] tabular-nums text-shell-muted">
          {ordered.length} run{ordered.length === 1 ? '' : 's'}
        </span>
      </div>
    </div>
  );
}

function RunCell({ cell }: { cell: MatrixCell }) {
  const tone = statusTone(cell.status);
  const title = [
    `run ${cell.runId.slice(0, 10)}`,
    `status ${cell.status}`,
    cell.durationMs != null ? `duration ${fmtMs(cell.durationMs)}` : null,
    cell.toolSteps > 0 ? `${cell.toolSteps} tool steps` : null,
    cell.startedAt ? fmtRelative(cell.startedAt) : null,
    cell.userMessage ? `\n"${cell.userMessage.slice(0, 80)}"` : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <span
      title={title}
      className={`inline-flex h-6 items-center gap-1 rounded-md border px-1.5 font-mono text-[10px] tabular-nums ${tone}`}
    >
      <StatusIcon status={cell.status} />
      <span>{fmtMs(cell.durationMs)}</span>
      {cell.toolSteps > 0 && (
        <span className="inline-flex items-center gap-0.5 text-[9px]">
          <Wrench className="h-2.5 w-2.5" />
          {cell.toolSteps}
        </span>
      )}
    </span>
  );
}

function Kpi({
  label,
  value,
  sub,
  icon: Icon,
  mono,
}: {
  label: string;
  value: string | number;
  sub: string;
  icon: typeof Activity;
  mono?: boolean;
}) {
  return (
    <div className="shell-page-utility-tile lift-sm rounded-[18px] border border-shell-border bg-shell-panel px-4 py-3 shadow-shell">
      <div className="mb-1.5 flex items-center justify-between">
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-shell-muted">
          {label}
        </span>
        <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-shell-accent-soft text-shell-accent">
          <Icon className="h-3 w-3" />
        </div>
      </div>
      <div
        className={`text-[1.5rem] font-semibold tracking-tight text-shell-text ${mono ? 'font-mono tabular-nums' : ''}`}
      >
        {value}
      </div>
      <div className="mt-0.5 font-mono text-[10px] tabular-nums text-shell-muted">{sub}</div>
    </div>
  );
}

function LegendDot({ tone, label }: { tone: 'success' | 'error' | 'live'; label: string }) {
  const cls =
    tone === 'success'
      ? 'bg-shell-success'
      : tone === 'error'
        ? 'bg-shell-error'
        : 'bg-shell-accent';
  return (
    <span className="inline-flex items-center gap-1">
      <span className={`h-2 w-2 rounded-full ${cls}`} />
      {label}
    </span>
  );
}

function FutureCard({
  icon: Icon,
  eyebrow,
  title,
  body,
}: {
  icon: typeof Swords;
  eyebrow: string;
  title: string;
  body: string;
}) {
  return (
    <div className="rounded-[18px] border border-dashed border-shell-border bg-shell-panel-strong/30 px-4 py-4 shadow-shell">
      <div className="mb-2 flex h-9 w-9 items-center justify-center rounded-lg border border-shell-accent/30 bg-shell-accent-soft text-shell-accent">
        <Icon className="h-4 w-4" />
      </div>
      <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.22em] text-shell-muted">
        {eyebrow}
      </div>
      <div className="mb-1.5 font-display text-lg text-shell-text">{title}</div>
      <p className="text-[12px] leading-relaxed text-shell-muted">{body}</p>
      <div className="mt-3 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.22em] text-shell-muted/70">
        draft
        <ArrowRight className="h-3 w-3" />
      </div>
    </div>
  );
}
