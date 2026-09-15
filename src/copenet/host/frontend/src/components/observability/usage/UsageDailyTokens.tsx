import { formatCount, formatTokens, type DailyTokenBar } from '../../../runtime/usageModel';
import { SERIES_VARS, SeriesLegend, UsageEmpty, UsagePanel } from './usageChrome';

/** One stacked bar per day, split by token kind.
 *
 *  The split is output / fresh input / cache read, and it sums to the day's total
 *  exactly once — cached input is a subset of input, so stacking `inputTokens`
 *  beside `cachedInputTokens` would count the whole cache twice. */
export function UsageDailyTokens({ bars }: { bars: DailyTokenBar[] }) {
  const busiest = bars.reduce((max, bar) => Math.max(max, bar.total), 0);
  const anyTokens = busiest > 0;

  return (
    <UsagePanel
      title="Tokens by day"
      subtitle={anyTokens ? `Peak ${formatTokens(busiest)} in a day` : undefined}
      actions={<SeriesLegend />}
    >
      {!anyTokens ? (
        <UsageEmpty>No provider reported token usage in this window.</UsageEmpty>
      ) : (
        <div className="overflow-x-auto">
          <div className="flex min-w-fit items-end gap-[3px]" style={{ height: '160px' }}>
            {bars.map((bar) => (
              <div key={bar.date} className="flex h-full min-w-[10px] flex-1 flex-col justify-end">
                <div
                  className="flex w-full flex-col-reverse overflow-hidden rounded-t-[3px]"
                  style={{ height: `${Math.max(bar.height * 100, bar.total > 0 ? 1.5 : 0)}%` }}
                  title={`${bar.label} · ${formatTokens(bar.total)} tokens · ${formatCount(bar.runs)} runs`}
                >
                  {bar.segments.map((segment) => (
                    <div
                      key={segment.kind}
                      // A 2px surface gap keeps adjacent segments legible instead of
                      // melting into one block at small heights.
                      style={{
                        height: `${segment.share * 100}%`,
                        background: SERIES_VARS[segment.kind],
                        boxShadow: '0 -2px 0 0 var(--color-shell-panel)',
                      }}
                    />
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div className="mt-1.5 flex min-w-fit gap-[3px]">
            {bars.map((bar, index) => (
              <div
                key={bar.date}
                className="min-w-[10px] flex-1 text-center font-mono text-[8px] text-shell-muted"
              >
                {index % Math.max(1, Math.ceil(bars.length / 10)) === 0 ? bar.label : ' '}
              </div>
            ))}
          </div>
        </div>
      )}
    </UsagePanel>
  );
}
