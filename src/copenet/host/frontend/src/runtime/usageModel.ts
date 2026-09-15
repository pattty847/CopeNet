import type {
  ObservabilityUsage,
  UsageCodingDay,
  UsageDayRow,
  UsageHourRow,
  UsageWeekdayRow,
} from '../types/backend';

/** Every derivation the Usage view draws from `observability.usage.get`.
 *
 *  Pure and exported so the shapes can be tested without a renderer. The one rule
 *  that runs through all of it: a null rate means nothing was measured, and it
 *  renders as an em dash — never as 0%, which would read as a real result. */

export const WEEKDAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;

/** The three token kinds a day is split into. They sum to input + output exactly
 *  once, because `freshInputTokens = inputTokens - cachedInputTokens`. */
export type TokenKind = 'output' | 'freshInput' | 'cacheRead';

export const TOKEN_KIND_LABELS: Record<TokenKind, string> = {
  output: 'Output',
  freshInput: 'Input (fresh)',
  cacheRead: 'Input (cache read)',
};

export function formatTokens(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value === 0) return '0';
  if (Math.abs(value) >= 1_000_000_000) return `${(value / 1_000_000_000).toFixed(1)}B`;
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(Math.round(value));
}

export function formatCount(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return value.toLocaleString();
}

/** A rate as a percent, or an em dash when the denominator was zero. */
export function formatRate(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—';
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSeconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  if (value < 60) return `${value.toFixed(1)}s`;
  const minutes = Math.floor(value / 60);
  return `${minutes}m ${Math.round(value - minutes * 60)}s`;
}

/** "Sep 15" — the short axis label for an ISO date, read in UTC so the label
 *  matches the date string the host bucketed by rather than the browser's day. */
export function formatDayLabel(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number);
  if (!year || !month || !day) return isoDate;
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    timeZone: 'UTC',
  });
}

export function formatHourLabel(hour: number): string {
  if (hour === 0) return '12a';
  if (hour === 12) return '12p';
  return hour < 12 ? `${hour}a` : `${hour - 12}p`;
}

export interface UsageTile {
  id: string;
  label: string;
  value: string;
  detail: string;
  /** `muted` marks a tile whose value is unknown rather than low. */
  tone: 'default' | 'muted' | 'warning';
}

/** The overview strip. Each tile says what it counted, because "12.4M tokens" with
 *  no denominator is the number an operator most easily misreads. */
export function buildUsageTiles(usage: ObservabilityUsage): UsageTile[] {
  const { totals, usageCoverage, coding } = usage;
  const coverageGap = usageCoverage.runsWithoutUsage > 0;
  return [
    {
      id: 'runs',
      label: 'Runs',
      value: formatCount(totals.runs),
      detail: `${formatCount(totals.sessions)} sessions · ${formatCount(totals.modelCalls)} model calls`,
      tone: 'default',
    },
    {
      id: 'tokens',
      label: 'Tokens',
      value: formatTokens(totals.totalTokens),
      detail: coverageGap
        ? `${formatCount(usageCoverage.runsWithUsage)} of ${formatCount(usageCoverage.runs)} runs reported usage`
        : `${formatTokens(totals.outputTokens)} out · ${formatTokens(totals.inputTokens)} in`,
      tone: coverageGap ? 'warning' : 'default',
    },
    {
      id: 'cache',
      label: 'Cache hit rate',
      value: formatRate(totals.cacheHitRate),
      detail:
        totals.cacheHitRate === null
          ? 'No provider reported input tokens'
          : `${formatTokens(totals.cachedInputTokens)} of ${formatTokens(totals.inputTokens)} input read from cache`,
      tone: totals.cacheHitRate === null ? 'muted' : 'default',
    },
    {
      id: 'tools',
      label: 'Tool calls',
      value: formatCount(totals.toolCalls),
      detail: `${formatCount(totals.distinctTools)} distinct tools · ${formatCount(totals.avgToolCallsPerRun ?? 0)} per run`,
      tone: 'default',
    },
    {
      id: 'errors',
      label: 'Run error rate',
      value: formatRate(totals.errorRate, 1),
      detail: `${formatCount(totals.errorRuns)} failed · ${formatCount(totals.toolBlocked)} tool calls blocked`,
      tone: (totals.errorRate ?? 0) > 0.1 ? 'warning' : 'default',
    },
    {
      id: 'peak',
      label: 'Peak context',
      value: formatTokens(totals.peakInputTokens || null),
      detail: `Largest single model call · ${formatTokens(totals.avgTokensPerRun)} avg per run`,
      tone: totals.peakInputTokens ? 'default' : 'muted',
    },
    {
      id: 'verified',
      label: 'Verified after edit',
      value: formatRate(coding.verifiedAfterEditRate),
      detail:
        coding.runsWithEdits === 0
          ? 'No run edited a file in this window'
          : `${formatCount(coding.runsVerifiedAfterLastEdit)} of ${formatCount(coding.runsWithEdits)} editing runs`,
      tone: coding.runsWithEdits === 0 ? 'muted' : (coding.verifiedAfterEditRate ?? 1) < 0.5 ? 'warning' : 'default',
    },
    {
      id: 'duration',
      label: 'Avg run time',
      value: formatSeconds(totals.avgRunSeconds),
      detail: totals.lastRunAt ? `Last run ${new Date(totals.lastRunAt).toLocaleString()}` : 'No runs in this window',
      tone: totals.avgRunSeconds === null ? 'muted' : 'default',
    },
  ];
}

export interface TokenSegment {
  kind: TokenKind;
  tokens: number;
  /** Share of the day's own total, so a stacked bar sums to 1 within the day. */
  share: number;
}

export interface DailyTokenBar {
  date: string;
  label: string;
  total: number;
  runs: number;
  segments: TokenSegment[];
  /** Share of the tallest day in the window — the bar's drawn height. */
  height: number;
}

/** The daily bar chart: one bar per day, stacked by token kind, scaled to the
 *  window's tallest day so the axis has one meaning across the whole chart. */
export function buildDailyTokenBars(daily: UsageDayRow[]): DailyTokenBar[] {
  const peak = daily.reduce((max, row) => Math.max(max, row.totalTokens), 0);
  return daily.map((row) => {
    const parts: Array<[TokenKind, number]> = [
      ['output', row.outputTokens],
      ['freshInput', row.freshInputTokens],
      ['cacheRead', row.cachedInputTokens],
    ];
    return {
      date: row.date,
      label: formatDayLabel(row.date),
      total: row.totalTokens,
      runs: row.runs,
      height: peak > 0 ? row.totalTokens / peak : 0,
      segments: parts
        .filter(([, tokens]) => tokens > 0)
        .map(([kind, tokens]) => ({ kind, tokens, share: row.totalTokens > 0 ? tokens / row.totalTokens : 0 })),
    };
  });
}

export interface CalendarCell {
  date: string;
  tokens: number;
  runs: number;
  /** 0 = nothing ran; 1–4 = quartile of the window's busiest day. */
  level: 0 | 1 | 2 | 3 | 4;
}

export interface CalendarWeek {
  /** Monday-first; leading/trailing days outside the window are null. */
  days: (CalendarCell | null)[];
  /** Month abbreviation when this column starts a new month, else null. */
  monthLabel: string | null;
}

/** GitHub-style columns of weeks. A day with runs but no reported tokens still
 *  gets level 1 — it happened, and a blank cell would say it did not. */
export function buildCalendarWeeks(daily: UsageDayRow[]): CalendarWeek[] {
  if (daily.length === 0) return [];
  const peak = daily.reduce((max, row) => Math.max(max, row.totalTokens), 0);
  const cells: CalendarCell[] = daily.map((row) => ({
    date: row.date,
    tokens: row.totalTokens,
    runs: row.runs,
    level: heatLevel(row.totalTokens, row.runs, peak),
  }));

  const weeks: CalendarWeek[] = [];
  let current: (CalendarCell | null)[] = new Array(weekdayIndex(cells[0].date)).fill(null);
  let lastMonth = '';
  for (const cell of cells) {
    current.push(cell);
    if (current.length === 7) {
      weeks.push({ days: current, monthLabel: null });
      current = [];
    }
  }
  if (current.length > 0) {
    weeks.push({ days: [...current, ...new Array(7 - current.length).fill(null)], monthLabel: null });
  }
  return weeks.map((week) => {
    const first = week.days.find((day): day is CalendarCell => day !== null);
    if (!first) return week;
    const month = first.date.slice(0, 7);
    if (month === lastMonth) return week;
    lastMonth = month;
    return { ...week, monthLabel: formatDayLabel(first.date).split(' ')[0] };
  });
}

function weekdayIndex(isoDate: string): number {
  const [year, month, day] = isoDate.split('-').map(Number);
  // getUTCDay is Sunday-first; the calendar column order is Monday-first.
  return (new Date(Date.UTC(year, month - 1, day)).getUTCDay() + 6) % 7;
}

export function heatLevel(tokens: number, runs: number, peak: number): 0 | 1 | 2 | 3 | 4 {
  if (runs === 0) return 0;
  if (peak <= 0 || tokens <= 0) return 1;
  const share = tokens / peak;
  if (share > 0.75) return 4;
  if (share > 0.5) return 3;
  if (share > 0.25) return 2;
  return 1;
}

export interface RhythmBar {
  key: string;
  label: string;
  runs: number;
  tokens: number;
  /** Share of the busiest bucket, so the row reads as a proportion. */
  share: number;
  peak: boolean;
}

/** Activity by weekday and by hour, each scaled to its own busiest bucket. The
 *  two charts never share a scale: they answer different questions. */
export function buildRhythm(
  weekday: UsageWeekdayRow[],
  hourly: UsageHourRow[],
): { weekday: RhythmBar[]; hourly: RhythmBar[] } {
  return {
    weekday: scaleRhythm(
      weekday.map((row) => ({
        key: String(row.weekday),
        label: WEEKDAY_LABELS[row.weekday] ?? String(row.weekday),
        runs: row.runs,
        tokens: row.totalTokens,
      })),
    ),
    hourly: scaleRhythm(
      hourly.map((row) => ({
        key: String(row.hour),
        label: formatHourLabel(row.hour),
        runs: row.runs,
        tokens: row.totalTokens,
      })),
    ),
  };
}

function scaleRhythm(rows: Array<Omit<RhythmBar, 'share' | 'peak'>>): RhythmBar[] {
  const peak = rows.reduce((max, row) => Math.max(max, row.runs), 0);
  return rows.map((row) => ({
    ...row,
    share: peak > 0 ? row.runs / peak : 0,
    peak: peak > 0 && row.runs === peak,
  }));
}

export interface HabitTrendPoint {
  date: string;
  label: string;
  /** Null on a day with no editing run — the rate has no denominator. */
  verifiedRate: number | null;
  redundantReads: number;
  blindRetries: number;
  toolCalls: number;
  runsWithEdits: number;
}

/** The coding-habits series: verification-after-edit as a rate, waste as counts.
 *  Days with no editing run keep a null rate so the line breaks instead of
 *  dropping to zero and inventing a bad day. */
export function buildHabitTrend(daily: UsageCodingDay[]): HabitTrendPoint[] {
  return daily.map((row) => ({
    date: row.date,
    label: formatDayLabel(row.date),
    verifiedRate: row.runsWithEdits > 0 ? row.verifiedAfterEditRate : null,
    redundantReads: row.redundantReads,
    blindRetries: row.blindRetries,
    toolCalls: row.toolCalls,
    runsWithEdits: row.runsWithEdits,
  }));
}
