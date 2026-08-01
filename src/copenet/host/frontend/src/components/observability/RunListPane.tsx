import { CheckCircle2, CircleDashed, Search, Wrench, XCircle } from 'lucide-react';
import type { Session, SessionRunRecord } from '../../types/backend';
import { formatCompactAge, formatRunDuration } from '../../lib/formatting';

interface RunListPaneProps {
  runs: SessionRunRecord[];
  sessions: Session[];
  selectedRunId: string | null;
  loading: boolean;
  query: string;
  onQueryChange: (query: string) => void;
  onSelect: (run: SessionRunRecord) => void;
}

function failed(run: SessionRunRecord): boolean {
  return Boolean(run.error) || run.status === 'error' || run.status === 'failed';
}

function RunStatus({ run }: { run: SessionRunRecord }) {
  if (failed(run)) return <XCircle className="h-3.5 w-3.5 text-shell-error" aria-label="Failed" />;
  if (!run.completedAt || run.status === 'running') {
    return <CircleDashed className="h-3.5 w-3.5 animate-spin text-shell-accent" aria-label="Running" />;
  }
  return <CheckCircle2 className="h-3.5 w-3.5 text-shell-success" aria-label="Completed" />;
}

export function RunListPane({
  runs,
  sessions,
  selectedRunId,
  loading,
  query,
  onQueryChange,
  onSelect,
}: RunListPaneProps) {
  const sessionTitles = new Map(sessions.map((session) => [session.key, session.title || session.key]));
  const normalizedQuery = query.trim().toLowerCase();
  const visibleRuns = runs.filter((run) => {
    if (!normalizedQuery) return true;
    return [
      run.userMessage,
      run.outputSummary,
      run.provider,
      run.model,
      run.runId,
      sessionTitles.get(run.sessionKey),
      ...run.toolSteps.map((step) => step.toolId),
    ]
      .some((value) => String(value || '').toLowerCase().includes(normalizedQuery));
  });

  return (
    <aside className="flex min-h-[34rem] min-w-0 flex-col border-b border-shell-border bg-shell-panel lg:border-b-0 lg:border-r">
      <div className="border-b border-shell-border px-3 py-3">
        <label className="relative block">
          <span className="sr-only">Search runs</span>
          <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-shell-muted" />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Search runs, models, tools…"
            className="focus-ring h-9 w-full rounded-lg border border-shell-border bg-shell-bg pl-9 pr-3 text-[12px] text-shell-text placeholder:text-shell-muted"
          />
        </label>
        <div className="mt-2 flex items-center justify-between font-mono text-[10px] tabular-nums text-shell-muted">
          <span>{visibleRuns.length} runs</span>
          <span>{loading ? 'refreshing…' : 'recent sessions'}</span>
        </div>
      </div>

      {visibleRuns.length === 0 ? (
        <div className="grid flex-1 place-items-center px-6 py-12 text-center text-[12px] leading-5 text-shell-muted">
          <p>{loading ? 'Loading recent runs…' : query ? 'No runs match this search.' : 'Runs appear after an agent turn completes.'}</p>
        </div>
      ) : (
        <ol className="max-h-[48rem] flex-1 overflow-y-auto" aria-label="Recent model runs">
          {visibleRuns.map((run) => {
            const selected = selectedRunId === run.runId;
            return (
              <li key={`${run.sessionKey}:${run.runId}`} className="border-b border-shell-border/60 last:border-b-0">
                <button
                  type="button"
                  onClick={() => onSelect(run)}
                  className={`focus-ring w-full px-3 py-3 text-left transition-colors ${
                    selected ? 'bg-shell-accent-soft' : 'hover:bg-shell-panel-strong/60'
                  }`}
                  aria-current={selected ? 'true' : undefined}
                >
                  <div className="flex items-center gap-2">
                    <RunStatus run={run} />
                    <span className="min-w-0 flex-1 truncate text-[12px] font-medium text-shell-text">
                      {sessionTitles.get(run.sessionKey) || run.sessionKey}
                    </span>
                    <span className="shrink-0 font-mono text-[10px] tabular-nums text-shell-muted">
                      {formatCompactAge(run.startedAt)}
                    </span>
                  </div>
                  <p className="mt-1.5 line-clamp-2 text-[11px] leading-4 text-shell-muted">
                    {run.userMessage || run.outputSummary || '(no message)'}
                  </p>
                  <div className="mt-2 flex items-center gap-2 font-mono text-[10px] tabular-nums text-shell-muted">
                    <span className="truncate text-shell-accent">{run.model || run.provider}</span>
                    <span>·</span>
                    <span>{formatRunDuration(run.startedAt, run.completedAt)}</span>
                    {run.toolSteps.length > 0 && (
                      <span className="ml-auto inline-flex items-center gap-1">
                        <Wrench className="h-3 w-3" />
                        {run.toolSteps.length}
                      </span>
                    )}
                  </div>
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </aside>
  );
}
