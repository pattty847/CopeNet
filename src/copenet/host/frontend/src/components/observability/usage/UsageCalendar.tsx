import {
  WEEKDAY_LABELS,
  formatCount,
  formatDayLabel,
  formatTokens,
  type CalendarWeek,
} from '../../../runtime/usageModel';
import { UsageEmpty, UsagePanel } from './usageChrome';

// A sequential ramp: one hue, five steps. Level 0 is an empty day and wears the
// surface, not the hue, so "nothing ran" never reads as "a little ran".
const LEVEL_STYLE = [
  'rgba(var(--usage-heat), 0.06)',
  'rgba(var(--usage-heat), 0.22)',
  'rgba(var(--usage-heat), 0.42)',
  'rgba(var(--usage-heat), 0.66)',
  'rgba(var(--usage-heat), 0.92)',
];

export function UsageCalendar({ weeks }: { weeks: CalendarWeek[] }) {
  const busiest = weeks
    .flatMap((week) => week.days)
    .reduce((max, day) => Math.max(max, day?.tokens ?? 0), 0);

  return (
    <UsagePanel
      title="Token activity"
      subtitle={busiest > 0 ? `Darkest cell = ${formatTokens(busiest)}` : undefined}
      actions={
        <div className="flex items-center gap-1.5 text-[9px] text-shell-muted">
          <span>Less</span>
          {LEVEL_STYLE.map((background, level) => (
            <span key={level} aria-hidden className="h-2.5 w-2.5 rounded-[2px]" style={{ background }} />
          ))}
          <span>More</span>
        </div>
      }
    >
      {weeks.length === 0 ? (
        <UsageEmpty>No days in this window.</UsageEmpty>
      ) : (
        <div className="overflow-x-auto">
          <div className="flex min-w-fit gap-[3px]">
            <div className="mr-1 flex flex-col gap-[3px] pt-[13px]">
              {WEEKDAY_LABELS.map((label, index) => (
                <span
                  key={label}
                  className="h-2.5 font-mono text-[8px] leading-[10px] text-shell-muted"
                  style={{ visibility: index % 2 === 0 ? 'visible' : 'hidden' }}
                >
                  {label}
                </span>
              ))}
            </div>
            {weeks.map((week, weekIndex) => (
              <div key={weekIndex} className="flex flex-col gap-[3px]">
                <span className="h-[10px] font-mono text-[8px] leading-[10px] text-shell-muted">
                  {week.monthLabel ?? ' '}
                </span>
                {week.days.map((day, dayIndex) => (
                  <span
                    key={day?.date ?? `${weekIndex}-${dayIndex}`}
                    className="h-2.5 w-2.5 rounded-[2px]"
                    style={{ background: day ? LEVEL_STYLE[day.level] : 'transparent' }}
                    title={
                      day
                        ? `${formatDayLabel(day.date)} · ${formatTokens(day.tokens)} tokens · ${formatCount(day.runs)} runs`
                        : undefined
                    }
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </UsagePanel>
  );
}
