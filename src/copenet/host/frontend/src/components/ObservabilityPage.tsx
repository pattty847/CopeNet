import { useEffect, useMemo, useState } from 'react';
import { Activity, RefreshCw, ShieldAlert, Wrench, Zap } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import type { SessionRunRecord } from '../types/backend';
import { RunPulseStrip } from './runtime/RunPulseStrip';
import { TraceList } from './runtime/TraceList';

const RUN_LOOKBACK_PER_SESSION = 10;
const REFRESH_MS = 12_000;

interface KpiTile {
  label: string;
  value: string;
  sub: string;
  icon: typeof Activity;
  tone: 'accent' | 'success' | 'error' | 'muted';
}

const TONE_CLASS: Record<KpiTile['tone'], string> = {
  accent: 'text-shell-accent',
  success: 'text-shell-success',
  error: 'text-shell-error',
  muted: 'text-shell-muted',
};

function runIsError(run: SessionRunRecord): boolean {
  return Boolean(run.error) || run.status === 'error' || run.status === 'failed';
}

function runIsCompleted(run: SessionRunRecord): boolean {
  return Boolean(run.completedAt) && !runIsError(run);
}

export function ObservabilityPage() {
  const sessions = useAppStore((s) => s.sessions);
  const providers = useAppStore((s) => s.providers);
  const [runs, setRuns] = useState<SessionRunRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [lastFetch, setLastFetch] = useState<number | null>(null);

  const activeSessions = useMemo(() => sessions.filter((s) => !s.archived), [sessions]);

  useEffect(() => {
    let cancelled = false;

    async function loadAll() {
      if (activeSessions.length === 0) {
        setRuns([]);
        setLastFetch(Date.now());
        return;
      }
      setLoading(true);
      try {
        const results = await Promise.all(
          activeSessions.map((s) =>
            wsClient.listSessionRuns(s.key, RUN_LOOKBACK_PER_SESSION).catch(() => [] as SessionRunRecord[]),
          ),
        );
        if (cancelled) return;
        const merged = results.flat();
        setRuns(merged);
        setLastFetch(Date.now());
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadAll();
    const timer = window.setInterval(loadAll, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeSessions]);

  const manualRefresh = () => {
    // Trigger re-run by nudging state; simplest is to re-call the effect deps.
    // We just re-fetch inline.
    (async () => {
      setLoading(true);
      const results = await Promise.all(
        activeSessions.map((s) =>
          wsClient.listSessionRuns(s.key, RUN_LOOKBACK_PER_SESSION).catch(() => [] as SessionRunRecord[]),
        ),
      );
      setRuns(results.flat());
      setLastFetch(Date.now());
      setLoading(false);
    })().catch(() => setLoading(false));
  };

  const stats = useMemo(() => {
    const dayAgo = Date.now() - 24 * 60 * 60 * 1000;
    const last24h = runs.filter((r) => new Date(r.startedAt).getTime() > dayAgo);
    const errors = last24h.filter(runIsError);
    const completed = last24h.filter(runIsCompleted);
    const totalSteps = last24h.reduce((acc, r) => acc + r.toolSteps.length, 0);
    const avgSteps = last24h.length > 0 ? totalSteps / last24h.length : 0;
    const totalDur = completed.reduce((acc, r) => {
      const end = r.completedAt ? new Date(r.completedAt).getTime() : new Date(r.startedAt).getTime();
      return acc + (end - new Date(r.startedAt).getTime());
    }, 0);
    const avgMs = completed.length > 0 ? totalDur / completed.length : 0;
    const providersUp = providers.filter((p) => p.available).length;

    return {
      runs24h: last24h.length,
      errors: errors.length,
      avgSteps: avgSteps.toFixed(1),
      avgLatencyS: avgMs > 0 ? (avgMs / 1000).toFixed(1) : '0.0',
      totalSteps,
      providersUp,
      providersTotal: providers.length,
    };
  }, [runs, providers]);

  const tiles: KpiTile[] = [
    {
      label: 'Runs · 24h',
      value: String(stats.runs24h),
      sub: `${stats.errors} error${stats.errors === 1 ? '' : 's'}`,
      icon: Zap,
      tone: stats.errors > 0 ? 'error' : 'accent',
    },
    {
      label: 'Tool steps · 24h',
      value: String(stats.totalSteps),
      sub: `${stats.avgSteps} avg per run`,
      icon: Wrench,
      tone: 'muted',
    },
    {
      label: 'Avg latency',
      value: `${stats.avgLatencyS}s`,
      sub: 'completed runs',
      icon: Activity,
      tone: 'muted',
    },
    {
      label: 'Providers up',
      value: `${stats.providersUp}/${stats.providersTotal || 0}`,
      sub: stats.providersUp === stats.providersTotal ? 'all healthy' : 'partial',
      icon: ShieldAlert,
      tone: stats.providersUp === stats.providersTotal && stats.providersTotal > 0 ? 'success' : 'error',
    },
  ];

  // Provider distribution for the bottom-right pane
  const providerDistribution = useMemo(() => {
    const byProvider = new Map<string, { total: number; errors: number }>();
    for (const r of runs) {
      const prev = byProvider.get(r.provider) ?? { total: 0, errors: 0 };
      prev.total += 1;
      if (runIsError(r)) prev.errors += 1;
      byProvider.set(r.provider, prev);
    }
    const list = [...byProvider.entries()]
      .map(([provider, v]) => ({ provider, ...v }))
      .sort((a, b) => b.total - a.total);
    const max = Math.max(1, ...list.map((x) => x.total));
    return { list, max };
  }, [runs]);

  const toolDistribution = useMemo(() => {
    const byTool = new Map<string, { total: number; errors: number }>();
    for (const r of runs) {
      for (const step of r.toolSteps) {
        const prev = byTool.get(step.toolId) ?? { total: 0, errors: 0 };
        prev.total += 1;
        if (!step.ok) prev.errors += 1;
        byTool.set(step.toolId, prev);
      }
    }
    const list = [...byTool.entries()]
      .map(([tool, v]) => ({ tool, ...v }))
      .sort((a, b) => b.total - a.total)
      .slice(0, 6);
    const max = Math.max(1, ...list.map((x) => x.total));
    return { list, max };
  }, [runs]);

  return (
    <div className="animate-fade-in-up space-y-3">
      {/* Condensed hero */}
      <section className="flex flex-wrap items-end justify-between gap-4 rounded-[20px] border border-shell-border bg-shell-panel px-6 py-5 shadow-shell">
        <div className="max-w-2xl">
          <div className="mb-2 inline-flex items-center gap-2 rounded-full border border-shell-accent/20 bg-shell-accent-soft px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
            <Activity className="h-3 w-3" />
            Observability
          </div>
          <h1 className="font-display text-[2rem] leading-[1.05] tracking-tight text-shell-text">
            Trace the work, not just the answer.
          </h1>
          <p className="mt-2 max-w-xl text-[13px] leading-6 text-shell-muted">
            Live view of every run across sessions. Tool blocks, provider drift, and latency are
            surfaced so the operator can understand what really happened.
          </p>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px] tabular-nums text-shell-muted">
          <span>
            last refresh{' '}
            <span className="text-shell-text">
              {lastFetch ? new Date(lastFetch).toLocaleTimeString([], { hour12: false }) : '—'}
            </span>
          </span>
          <button
            type="button"
            onClick={manualRefresh}
            className="focus-ring inline-flex items-center gap-1.5 rounded-lg border border-shell-border bg-shell-panel-strong px-2.5 py-1.5 text-[11px] text-shell-text transition-colors hover:border-shell-accent/40 hover:text-shell-accent"
            title="Refresh now"
          >
            <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
            refresh
          </button>
        </div>
      </section>

      {/* KPI row */}
      <section className="stagger-children grid gap-2.5 md:grid-cols-2 xl:grid-cols-4">
        {tiles.map((t) => {
          const Icon = t.icon;
          return (
            <div
              key={t.label}
              className="lift-sm rounded-[20px] border border-shell-border bg-shell-panel px-4 py-4 shadow-shell"
            >
              <div className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-muted">
                <span>{t.label}</span>
                <Icon className={`h-3.5 w-3.5 ${TONE_CLASS[t.tone]}`} />
              </div>
              <div className={`font-mono text-[30px] font-medium leading-none tabular-nums ${TONE_CLASS[t.tone]}`}>
                {t.value}
              </div>
              <div className="mt-2 font-mono text-[11px] tabular-nums text-shell-muted">{t.sub}</div>
            </div>
          );
        })}
      </section>

      {/* Pulse strip */}
      <RunPulseStrip runs={runs} loading={loading && runs.length === 0} />

      {/* Two-column bottom row */}
      <section className="grid gap-3 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <TraceList runs={runs} />

        <div className="space-y-3">
          {/* Provider distribution */}
          <section className="rounded-[20px] border border-shell-border bg-shell-panel px-5 py-4 shadow-shell">
            <header className="mb-3 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
                By provider
              </span>
              <span className="font-mono text-[11px] tabular-nums text-shell-muted">24h</span>
            </header>
            {providerDistribution.list.length === 0 ? (
              <div className="py-4 text-center text-[12px] text-shell-muted">No runs recorded yet.</div>
            ) : (
              <ul className="space-y-2">
                {providerDistribution.list.map((row) => {
                  const pct = Math.max(4, (row.total / providerDistribution.max) * 100);
                  const errPct = row.total > 0 ? (row.errors / row.total) * 100 : 0;
                  return (
                    <li key={row.provider} className="font-mono text-[11px] tabular-nums">
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-shell-text">{row.provider}</span>
                        <span className="text-shell-muted">
                          {row.total}
                          {row.errors > 0 && <span className="text-shell-error"> · {row.errors} err</span>}
                        </span>
                      </div>
                      <div className="relative h-1.5 overflow-hidden rounded-full bg-shell-border-strong/40">
                        <div
                          className="absolute inset-y-0 left-0 bg-shell-accent/70"
                          style={{ width: `${pct}%` }}
                        />
                        {errPct > 0 && (
                          <div
                            className="absolute inset-y-0 left-0 bg-shell-error/80"
                            style={{ width: `${(pct * errPct) / 100}%` }}
                          />
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          {/* Tool distribution */}
          <section className="rounded-[20px] border border-shell-border bg-shell-panel px-5 py-4 shadow-shell">
            <header className="mb-3 flex items-center justify-between">
              <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">
                Top tools
              </span>
              <span className="font-mono text-[11px] tabular-nums text-shell-muted">{stats.totalSteps} steps</span>
            </header>
            {toolDistribution.list.length === 0 ? (
              <div className="py-4 text-center text-[12px] text-shell-muted">
                No tool invocations captured yet.
              </div>
            ) : (
              <ul className="space-y-2">
                {toolDistribution.list.map((row) => {
                  const pct = Math.max(4, (row.total / toolDistribution.max) * 100);
                  return (
                    <li key={row.tool} className="font-mono text-[11px] tabular-nums">
                      <div className="mb-1 flex items-center justify-between">
                        <span className="truncate text-shell-text">{row.tool}</span>
                        <span className="text-shell-muted">
                          {row.total}
                          {row.errors > 0 && <span className="text-shell-error"> · {row.errors}</span>}
                        </span>
                      </div>
                      <div className="h-1.5 overflow-hidden rounded-full bg-shell-border-strong/40">
                        <div className="h-full bg-shell-accent/70" style={{ width: `${pct}%` }} />
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        </div>
      </section>
    </div>
  );
}
