import { useMemo } from 'react';
import { CheckCircle2, CircleDashed, XCircle, Wrench } from 'lucide-react';
import type { SessionRunRecord } from '../../types/backend';

interface TraceListProps {
  runs: SessionRunRecord[];
  limit?: number;
  onSelect?: (runId: string) => void;
}

function formatDur(run: SessionRunRecord): string {
  if (!run.completedAt) return '—';
  const ms = new Date(run.completedAt).getTime() - new Date(run.startedAt).getTime();
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${Math.floor(ms / 60_000)}m${Math.floor((ms % 60_000) / 1000)
    .toString()
    .padStart(2, '0')}s`;
}

function timeAgo(iso: string): string {
  const diffS = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (diffS < 60) return `${diffS}s`;
  if (diffS < 3600) return `${Math.floor(diffS / 60)}m`;
  if (diffS < 86400) return `${Math.floor(diffS / 3600)}h`;
  return `${Math.floor(diffS / 86400)}d`;
}

function StatusIcon({ run }: { run: SessionRunRecord }) {
  if (run.error || run.status === 'error' || run.status === 'failed') {
    return <XCircle className="h-3.5 w-3.5 text-shell-error" />;
  }
  if (!run.completedAt || run.status === 'running') {
    return <CircleDashed className="h-3.5 w-3.5 text-shell-accent animate-spin" />;
  }
  return <CheckCircle2 className="h-3.5 w-3.5 text-shell-success" />;
}

export function TraceList({ runs, limit = 12, onSelect }: TraceListProps) {
  const recent = useMemo(
    () =>
      [...runs]
        .sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())
        .slice(0, limit),
    [runs, limit],
  );

  return (
    <section className="rounded-[20px] border border-shell-border bg-shell-panel px-5 py-4 shadow-shell">
      <header className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Recent traces</span>
          <span className="font-mono text-[11px] tabular-nums text-shell-muted">{runs.length} total</span>
        </div>
      </header>

      {recent.length === 0 ? (
        <div className="py-8 text-center text-[12px] text-shell-muted">
          Traces appear here as runs complete across all sessions.
        </div>
      ) : (
        <ul className="divide-y divide-shell-border/60">
          {recent.map((run) => {
            const failed = run.error || run.status === 'error' || run.status === 'failed';
            const running = !run.completedAt || run.status === 'running';
            return (
              <li key={run.runId}>
                <button
                  type="button"
                  onClick={() => onSelect?.(run.runId)}
                  className="interactive-row group flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left"
                >
                  <StatusIcon run={run} />
                  <span className="font-mono text-[11px] tabular-nums text-shell-accent">
                    {run.runId.slice(0, 10)}
                  </span>
                  <span className="truncate text-[12px] text-shell-text">
                    {run.userMessage || run.outputSummary || '(no message)'}
                  </span>
                  <span className="ml-auto flex shrink-0 items-center gap-3 font-mono text-[11px] tabular-nums text-shell-muted">
                    {run.toolSteps.length > 0 && (
                      <span className="inline-flex items-center gap-1">
                        <Wrench className="h-3 w-3" />
                        {run.toolSteps.length}
                      </span>
                    )}
                    <span className="w-10 text-right">{formatDur(run)}</span>
                    <span className="w-6 text-right">{timeAgo(run.startedAt)}</span>
                    <span
                      className={`w-12 text-right uppercase tracking-wider ${
                        failed ? 'text-shell-error' : running ? 'text-shell-accent' : 'text-shell-success/80'
                      }`}
                    >
                      {failed ? 'err' : running ? 'live' : 'ok'}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
