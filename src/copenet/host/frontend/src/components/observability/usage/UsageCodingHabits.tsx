import { formatCount, formatRate, type HabitTrendPoint } from '../../../runtime/usageModel';
import type { UsageCodingTotals } from '../../../types/backend';
import { StatRow, UsageEmpty, UsagePanel } from './usageChrome';

/** Coding habits over the window.
 *
 *  These are CopeNet's own numbers, not a token dashboard's: every run already
 *  carries `codingMetrics` from `core/harness/coding_metrics.py`, so the same
 *  rules that grade a benchmark run grade a real session here.
 *
 *  The verification line breaks on days with no editing run rather than dropping
 *  to zero — a day where the agent never edited anything did not fail to verify. */
export function UsageCodingHabits({
  coding,
  trend,
}: {
  coding: UsageCodingTotals;
  trend: HabitTrendPoint[];
}) {
  if (coding.runsWithMetrics === 0) {
    return (
      <UsagePanel title="Coding habits" subtitle="From each run's own tool calls">
        <UsageEmpty>No run in this window called a tool, so there are no coding metrics.</UsageEmpty>
      </UsagePanel>
    );
  }

  return (
    <div className="grid gap-2 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
      <UsagePanel
        title="Verification after the last edit"
        subtitle={`${formatCount(coding.runsWithEdits)} editing runs · ${formatRate(coding.verifiedAfterEditRate)} verified`}
      >
        <VerificationTrend points={trend} />
      </UsagePanel>

      <UsagePanel title="Where the calls went" subtitle={`${formatCount(coding.runsWithMetrics)} runs with tool calls`}>
        <div>
          <StatRow
            label="Redundant reads"
            value={formatCount(coding.redundantReads)}
            hint="A range the agent had already read in the same run."
          />
          <StatRow
            label="Reads after its own edit"
            value={formatCount(coding.readsAfterOwnEdit)}
            hint="Re-reading a file the agent itself just wrote."
          />
          <StatRow
            label="Searches over the cap"
            value={`${formatCount(coding.searchDumps)} of ${formatCount(coding.searches)}`}
            hint="files.rg results clipped by the hard match cap."
          />
          <StatRow label="Exact repeats" value={formatCount(coding.exactRepeats)} hint="The identical call, twice." />
          <StatRow
            label="Blind retries"
            value={formatCount(coding.blindRetries)}
            hint="A failed call retried unchanged."
          />
          <StatRow label="Stale edit refusals" value={formatCount(coding.staleEdits)} />
          <StatRow
            label="Blocked by policy"
            value={formatCount(coding.blocked)}
            hint="The model asked; policy_for_task_mode refused."
          />
          <StatRow
            label="Recovered after a red run"
            value={`${formatCount(coding.editsAfterFailedVerification)} of ${formatCount(coding.failedVerificationsAfterEdit)}`}
            hint="Failed verifications the agent then edited in response to."
          />
        </div>
      </UsagePanel>
    </div>
  );
}

/** A 100%-height column per day: filled share = verified, hollow = not. Days with
 *  no editing run are drawn as an empty slot, not as a zero-height bar. */
function VerificationTrend({ points }: { points: HabitTrendPoint[] }) {
  const anyEdits = points.some((point) => point.runsWithEdits > 0);
  if (!anyEdits) {
    return <UsageEmpty>No run edited a file in this window.</UsageEmpty>;
  }
  return (
    <div className="overflow-x-auto">
      <div className="flex min-w-fit items-end gap-[3px]" style={{ height: '120px' }}>
        {points.map((point) => (
          <div
            key={point.date}
            className="flex h-full min-w-[10px] flex-1 flex-col justify-end"
            title={
              point.verifiedRate === null
                ? `${point.label} · no editing run`
                : `${point.label} · ${formatRate(point.verifiedRate)} of ${formatCount(point.runsWithEdits)} editing runs verified`
            }
          >
            {point.verifiedRate === null ? (
              <div className="h-full w-full rounded-[3px] border border-dashed border-shell-border" />
            ) : (
              <div className="h-full w-full overflow-hidden rounded-[3px] bg-shell-bg">
                <div className="h-full w-full" style={{ transform: `translateY(${(1 - point.verifiedRate) * 100}%)`, background: 'var(--usage-series-cache)' }} />
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="mt-1.5 flex min-w-fit gap-[3px]">
        {points.map((point, index) => (
          <span key={point.date} className="min-w-[10px] flex-1 text-center font-mono text-[8px] text-shell-muted">
            {index % Math.max(1, Math.ceil(points.length / 10)) === 0 ? point.label : ' '}
          </span>
        ))}
      </div>
      <p className="mt-2 text-[10px] text-shell-muted">
        Filled = the share of that day&apos;s editing runs that ran a test, lint, type-check or build after their last
        edit. A dashed slot is a day with no editing run, not a day that failed to verify.
      </p>
    </div>
  );
}
