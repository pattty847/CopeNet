import { useCallback, useEffect, useMemo, useState } from 'react';
import { BarChart3, FlaskConical, RefreshCw } from 'lucide-react';
import { SectionHead } from '../../SectionHead';
import { wsClient } from '../../../lib/wsClient';
import type { ObservabilityUsage } from '../../../types/backend';
import {
  buildCalendarWeeks,
  buildDailyTokenBars,
  buildHabitTrend,
  buildRhythm,
  buildUsageTiles,
  formatCount,
} from '../../../runtime/usageModel';
import { UsageCalendar } from './UsageCalendar';
import { UsageCodingHabits } from './UsageCodingHabits';
import { UsageDailyTokens } from './UsageDailyTokens';
import { UsageRhythm } from './UsageRhythm';
import { UsageTiles } from './UsageTiles';
import { UsageTopLists } from './UsageTopLists';

const RANGES = [7, 30, 90, 365] as const;
type Range = (typeof RANGES)[number];

function rangeLabel(days: Range): string {
  return days === 365 ? '1y' : `${days}d`;
}

/** The Usage view: what the durable run records add up to over a window.
 *
 *  Loading, empty and error are three distinct states and none of them shows a
 *  number. There is no demo data here — an empty window says so. */
export function UsageView({ tabs }: { tabs: React.ReactNode }) {
  const [days, setDays] = useState<Range>(30);
  const [includeBench, setIncludeBench] = useState(false);
  const [usage, setUsage] = useState<ObservabilityUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (nextDays: Range, nextIncludeBench: boolean, showSpinner: boolean) => {
    if (showSpinner) setLoading(true);
    setError(null);
    try {
      setUsage(await wsClient.getObservabilityUsage(nextDays, nextIncludeBench));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'Could not load the usage rollup.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(days, includeBench, true);
  }, [days, includeBench, load]);

  const derived = useMemo(() => {
    if (!usage) return null;
    return {
      tiles: buildUsageTiles(usage),
      bars: buildDailyTokenBars(usage.daily),
      weeks: buildCalendarWeeks(usage.daily),
      rhythm: buildRhythm(usage.weekday, usage.hourly),
      trend: buildHabitTrend(usage.coding.daily),
    };
  }, [usage]);

  const context = usage
    ? `${formatCount(usage.totals.runs)} runs · ${usage.range.start} → ${usage.range.end}`
    : loading
      ? 'Reading run records…'
      : 'No data';

  return (
    <div className="animate-fade-in-up space-y-2">
      <SectionHead icon={BarChart3} title="Usage" context={context}>
        <div className="flex flex-wrap items-center gap-2 self-center">
          {tabs}
          <div className="flex items-center gap-0.5 rounded-lg border border-shell-border bg-shell-panel p-0.5">
            {RANGES.map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setDays(option)}
                aria-pressed={days === option}
                className={`focus-ring rounded-md px-2 py-1 font-mono text-[10px] transition-colors ${
                  days === option ? 'bg-shell-accent-soft text-shell-accent' : 'text-shell-muted hover:text-shell-text'
                }`}
              >
                {rangeLabel(option)}
              </button>
            ))}
          </div>
          <button
            type="button"
            role="switch"
            aria-checked={includeBench}
            onClick={() => setIncludeBench((value) => !value)}
            className={`focus-ring inline-flex h-8 items-center gap-2 rounded-lg border px-3 text-[11px] transition-colors ${
              includeBench
                ? 'border-shell-accent/30 bg-shell-accent-soft text-shell-accent'
                : 'border-shell-border bg-shell-panel text-shell-muted hover:text-shell-text'
            }`}
            title="Benchmark suites run in sessions prefixed bench-. They are real runs, but they are not your own work."
          >
            <FlaskConical className="h-3.5 w-3.5" />
            Benchmark runs {includeBench ? 'in' : 'out'}
          </button>
          <button
            type="button"
            onClick={() => void load(days, includeBench, false)}
            className="focus-ring inline-flex h-8 items-center gap-2 rounded-lg border border-shell-border bg-shell-panel px-3 text-[11px] text-shell-muted transition-colors hover:text-shell-text"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </SectionHead>

      {error && (
        <div role="alert" className="rounded-lg border border-shell-error/30 bg-shell-error/5 px-3 py-2 text-[11px] text-shell-error">
          {error}
        </div>
      )}

      {loading && !usage && <UsageSkeleton />}

      {!loading && !error && usage && usage.totals.runs === 0 && (
        <div className="rounded-xl border border-shell-border bg-shell-panel px-4 py-10 text-center">
          <p className="text-[12px] text-shell-text">No runs in the last {rangeLabel(days)}.</p>
          <p className="mt-1 text-[11px] text-shell-muted">
            {usage.benchRunsExcluded > 0
              ? `${formatCount(usage.benchRunsExcluded)} benchmark runs were excluded — turn them on to include them.`
              : 'Send a message in Agents and this fills in.'}
          </p>
        </div>
      )}

      {usage && derived && usage.totals.runs > 0 && (
        <>
          <UsageTiles tiles={derived.tiles} />
          <UsageDailyTokens bars={derived.bars} />
          <UsageCalendar weeks={derived.weeks} />
          <UsageRhythm weekday={derived.rhythm.weekday} hourly={derived.rhythm.hourly} />
          <UsageTopLists models={usage.models} providers={usage.providers} tools={usage.tools} />
          <UsageCodingHabits coding={usage.coding} trend={derived.trend} />
          <UsageProvenance usage={usage} />
        </>
      )}
    </div>
  );
}

/** What the numbers above are and are not. Every line here is a real limit of the
 *  data, not a disclaimer: a reader who does not know that usage is provider-
 *  reported will read a missing provider as a cheap one. */
function UsageProvenance({ usage }: { usage: ObservabilityUsage }) {
  const { usageCoverage, benchRunsExcluded, undatedRunsSkipped, range } = usage;
  return (
    <p className="px-1 pb-2 text-[10px] leading-relaxed text-shell-muted">
      Grouped from durable run records between {range.start} and {range.end}
      {range.timezone ? ` (${range.timezone})` : ''}. Token counts are what the provider reported —{' '}
      {usageCoverage.runsWithoutUsage > 0
        ? `${formatCount(usageCoverage.runsWithoutUsage)} of ${formatCount(usageCoverage.runs)} runs reported none and contribute zero`
        : 'every run in this window reported usage'}
      . Cached input is a subset of input, so the daily split is output / fresh input / cache read. No costs: CopeNet
      runs on subscriptions.
      {benchRunsExcluded > 0 ? ` ${formatCount(benchRunsExcluded)} benchmark runs excluded.` : ''}
      {undatedRunsSkipped > 0 ? ` ${formatCount(undatedRunsSkipped)} runs had an unreadable timestamp and were skipped.` : ''}
    </p>
  );
}

function UsageSkeleton() {
  return (
    <div className="space-y-2" aria-busy="true" aria-label="Loading usage">
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 8 }, (_, index) => (
          <div key={index} className="h-[74px] rounded-xl border border-shell-border bg-shell-panel shimmer" />
        ))}
      </div>
      <div className="h-[220px] rounded-xl border border-shell-border bg-shell-panel shimmer" />
      <div className="h-[140px] rounded-xl border border-shell-border bg-shell-panel shimmer" />
    </div>
  );
}
