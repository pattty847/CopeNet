import { useMemo, useState } from 'react';
import type { SessionRunRecord } from '../../types/backend';

interface RunPulseStripProps {
  runs: SessionRunRecord[];
  loading?: boolean;
  cellCount?: number;
}

type StatusTone = 'success' | 'error' | 'running' | 'empty';

function runStatusTone(run: SessionRunRecord): StatusTone {
  if (run.status === 'completed' || run.status === 'ok') return 'success';
  if (run.status === 'error' || run.status === 'failed' || run.error) return 'error';
  if (run.status === 'running' || run.status === 'in_flight') return 'running';
  return run.completedAt ? 'success' : 'running';
}

const TONE_CLASS: Record<StatusTone, string> = {
  success: 'bg-shell-success/75 hover:bg-shell-success',
  error: 'bg-shell-error/80 hover:bg-shell-error',
  running: 'bg-shell-accent/70 hover:bg-shell-accent',
  empty: 'bg-shell-border-strong/40',
};

function formatDuration(run: SessionRunRecord): string {
  if (!run.completedAt) return '—';
  const start = new Date(run.startedAt).getTime();
  const end = new Date(run.completedAt).getTime();
  const ms = Math.max(0, end - start);
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.floor(s % 60);
  return `${m}m${rem.toString().padStart(2, '0')}s`;
}

function formatTimeOfDay(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
}

export function RunPulseStrip({ runs, loading = false, cellCount = 72 }: RunPulseStripProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  const cells = useMemo(() => {
    const recent = [...runs]
      .sort((a, b) => new Date(b.startedAt).getTime() - new Date(a.startedAt).getTime())
      .slice(0, cellCount)
      .reverse(); // oldest → newest for left-to-right time flow
    const pad = Math.max(0, cellCount - recent.length);
    return [
      ...Array.from({ length: pad }, () => null),
      ...recent,
    ];
  }, [runs, cellCount]);

  const hoveredRun = hoverIndex !== null ? cells[hoverIndex] : null;

  return (
    <section className="rounded-[20px] border border-shell-border bg-shell-panel px-5 py-4 shadow-shell">
      <header className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="relative flex h-1.5 w-1.5">
            <span className="pulse-live absolute inline-flex h-full w-full rounded-full bg-shell-accent opacity-70" />
            <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-shell-accent" />
          </span>
          <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-shell-accent">Run pulse</span>
          <span className="text-[11px] text-shell-muted">last {cellCount} · newest on right</span>
        </div>
        <div className="flex items-center gap-3 font-mono text-[11px] tabular-nums text-shell-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-shell-success/75" />
            ok
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-shell-error/80" />
            err
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-sm bg-shell-accent/70" />
            live
          </span>
        </div>
      </header>

      <div
        className="grid gap-[3px]"
        style={{ gridTemplateColumns: `repeat(${cellCount}, minmax(0, 1fr))` }}
        onMouseLeave={() => setHoverIndex(null)}
      >
        {cells.map((run, i) => {
          const tone: StatusTone = run ? runStatusTone(run) : 'empty';
          return (
            <button
              key={i}
              type="button"
              className={`h-8 rounded-[3px] transition-all duration-150 ${TONE_CLASS[tone]} ${
                hoverIndex === i ? 'ring-2 ring-shell-accent/50 scale-y-110' : ''
              } ${loading && !run ? 'shimmer' : ''}`}
              onMouseEnter={() => setHoverIndex(i)}
              aria-label={run ? `Run ${run.runId}` : 'No run'}
            />
          );
        })}
      </div>

      <div className="mt-3 min-h-[42px] font-mono text-[11px] tabular-nums">
        {hoveredRun ? (
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-shell-text">
            <span className="text-shell-accent">{hoveredRun.runId.slice(0, 10)}</span>
            <span className="text-shell-muted">{formatTimeOfDay(hoveredRun.startedAt)}</span>
            <span className="text-shell-muted">dur {formatDuration(hoveredRun)}</span>
            <span className="text-shell-muted">
              {hoveredRun.provider}
              {hoveredRun.model ? ` · ${hoveredRun.model}` : ''}
            </span>
            <span className="text-shell-muted">{hoveredRun.toolSteps.length} steps</span>
            <span
              className={`uppercase tracking-wider ${
                runStatusTone(hoveredRun) === 'error'
                  ? 'text-shell-error'
                  : runStatusTone(hoveredRun) === 'running'
                    ? 'text-shell-accent'
                    : 'text-shell-success'
              }`}
            >
              {hoveredRun.status || (hoveredRun.completedAt ? 'ok' : 'running')}
            </span>
          </div>
        ) : (
          <div className="text-[11px] text-shell-muted">
            {runs.length === 0
              ? loading
                ? 'Collecting traces…'
                : 'No runs yet. Kick one off from Agents and it will light up here.'
              : 'Hover a cell for trace detail'}
          </div>
        )}
      </div>
    </section>
  );
}
