import { formatCount, formatTokens, type RhythmBar } from '../../../runtime/usageModel';
import { UsageEmpty, UsagePanel } from './usageChrome';

/** When the operator works: runs by weekday and runs by hour of day.
 *
 *  Both charts count RUNS, not tokens — the question is rhythm, and one long
 *  agentic run would otherwise outweigh a whole afternoon of short ones. Each
 *  chart is scaled to its own busiest bucket; they never share an axis. */
export function UsageRhythm({ weekday, hourly }: { weekday: RhythmBar[]; hourly: RhythmBar[] }) {
  const anyRuns = weekday.some((bar) => bar.runs > 0);
  return (
    <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
      <UsagePanel title="By day of week" subtitle="Runs">
        {!anyRuns ? (
          <UsageEmpty>No runs in this window.</UsageEmpty>
        ) : (
          <div className="space-y-1">
            {weekday.map((bar) => (
              <div key={bar.key} className="flex items-center gap-2">
                <span className="w-7 font-mono text-[10px] text-shell-muted">{bar.label}</span>
                <div className="h-2.5 flex-1 overflow-hidden rounded-[3px] bg-shell-bg">
                  <div
                    className="h-full rounded-[3px]"
                    style={{
                      width: `${Math.max(bar.share * 100, bar.runs > 0 ? 2 : 0)}%`,
                      background: bar.peak ? 'var(--usage-series-output)' : 'rgba(var(--usage-heat), 0.45)',
                    }}
                  />
                </div>
                <span className="w-8 text-right font-mono text-[10px] text-shell-text" title={`${formatTokens(bar.tokens)} tokens`}>
                  {formatCount(bar.runs)}
                </span>
              </div>
            ))}
          </div>
        )}
      </UsagePanel>

      <UsagePanel title="By hour of day" subtitle="Runs, in the host's local time">
        {!hourly.some((bar) => bar.runs > 0) ? (
          <UsageEmpty>No runs in this window.</UsageEmpty>
        ) : (
          <>
            <div className="flex items-end gap-[3px]" style={{ height: '96px' }}>
              {hourly.map((bar) => (
                <div
                  key={bar.key}
                  className="flex h-full flex-1 flex-col justify-end"
                  title={`${bar.label} · ${formatCount(bar.runs)} runs · ${formatTokens(bar.tokens)} tokens`}
                >
                  <div
                    className="w-full rounded-t-[3px]"
                    style={{
                      height: `${Math.max(bar.share * 100, bar.runs > 0 ? 3 : 0)}%`,
                      background: bar.peak ? 'var(--usage-series-output)' : 'rgba(var(--usage-heat), 0.45)',
                    }}
                  />
                </div>
              ))}
            </div>
            <div className="mt-1.5 flex gap-[3px]">
              {hourly.map((bar, index) => (
                <span key={bar.key} className="flex-1 text-center font-mono text-[8px] text-shell-muted">
                  {index % 3 === 0 ? bar.label : ' '}
                </span>
              ))}
            </div>
          </>
        )}
      </UsagePanel>
    </div>
  );
}
