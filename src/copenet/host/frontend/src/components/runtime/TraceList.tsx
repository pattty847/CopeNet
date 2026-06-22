import { useMemo } from 'react';
import { useIsMobile } from '../../lib/responsive';
import { clampResponsiveText } from '../../lib/mobileCopy';
import { formatCompactAge, formatRunDuration } from '../../lib/formatting';
import { CheckCircle2, CircleDashed, XCircle, Wrench } from 'lucide-react';
import type { SessionRunRecord } from '../../types/backend';

interface TraceListProps {
  runs: SessionRunRecord[];
  limit?: number;
  onSelect?: (runId: string) => void;
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
  const isMobile = useIsMobile();

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
                  <span className="shrink-0 font-mono text-[11px] tabular-nums text-shell-accent">
                    {run.runId.slice(0, 10)}
                  </span>
                  <span
                    className="block min-w-0 flex-1 truncate text-[12px] text-shell-text"
                    title={run.userMessage || run.outputSummary || '(no message)'}
                  >
                    {clampResponsiveText(run.userMessage || run.outputSummary || '(no message)', {
                      isMobile,
                      mobileLimit: 42,
                      desktopLimit: 110,
                    })}
                  </span>
                  <span className="ml-auto hidden shrink-0 items-center gap-3 font-mono text-[11px] tabular-nums text-shell-muted sm:flex">
                    {run.toolSteps.length > 0 && (
                      <span className="inline-flex items-center gap-1">
                        <Wrench className="h-3 w-3" />
                        {run.toolSteps.length}
                      </span>
                    )}
                    <span className="w-10 text-right">{formatRunDuration(run.startedAt, run.completedAt)}</span>
                    <span className="w-6 text-right">{formatCompactAge(run.startedAt)}</span>
                    <span
                      className={`w-12 text-right uppercase tracking-wider ${
                        failed ? 'text-shell-error' : running ? 'text-shell-accent' : 'text-shell-success/80'
                      }`}
                    >
                      {failed ? 'err' : running ? 'live' : 'ok'}
                    </span>
                  </span>
                  <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-shell-muted sm:hidden">
                    {failed ? 'err' : running ? 'live' : 'ok'}
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
