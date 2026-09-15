import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildCalendarWeeks,
  buildDailyTokenBars,
  buildHabitTrend,
  buildRhythm,
  buildUsageTiles,
  formatRate,
  formatTokens,
  heatLevel,
} from '../src/runtime/usageModel';
import type {
  ObservabilityUsage,
  UsageCodingDay,
  UsageDayRow,
  UsageHourRow,
  UsageTokenTotals,
  UsageWeekdayRow,
} from '../src/types/backend';

function totals(overrides: Partial<UsageTokenTotals> = {}): UsageTokenTotals {
  return {
    runs: 0,
    runsWithUsage: 0,
    modelCalls: 0,
    toolCalls: 0,
    errorRuns: 0,
    errorRate: null,
    inputTokens: 0,
    cachedInputTokens: 0,
    freshInputTokens: 0,
    outputTokens: 0,
    reasoningTokens: 0,
    peakInputTokens: 0,
    totalTokens: 0,
    cacheHitRate: null,
    sessions: 0,
    ...overrides,
  };
}

function codingDay(date: string, overrides: Partial<UsageCodingDay> = {}): UsageCodingDay {
  return {
    date,
    runsWithMetrics: 0,
    toolCalls: 0,
    redundantReads: 0,
    blindRetries: 0,
    edits: 0,
    runsWithEdits: 0,
    runsVerifiedAfterLastEdit: 0,
    verifiedAfterEditRate: null,
    ...overrides,
  };
}

function day(date: string, overrides: Partial<UsageDayRow> = {}): UsageDayRow {
  const { coding, ...rest } = overrides;
  const { date: _ignored, ...codingRest } = codingDay(date);
  return {
    date,
    ...totals(),
    coding: { ...codingRest, ...(coding ?? {}) },
    ...rest,
  } as UsageDayRow;
}

function usageFixture(overrides: Partial<ObservabilityUsage> = {}): ObservabilityUsage {
  return {
    range: { days: 3, start: '2026-09-13', end: '2026-09-15', generatedAt: '2026-09-15T18:00:00+00:00', timezone: 'UTC' },
    includeBench: false,
    benchRunsExcluded: 0,
    undatedRunsSkipped: 0,
    totals: {
      ...totals(),
      toolFailures: 0,
      toolBlocked: 0,
      toolFailureRate: null,
      distinctTools: 0,
      avgToolCallsPerRun: null,
      avgTokensPerRun: null,
      avgOutputTokensPerRun: null,
      avgRunSeconds: null,
      firstRunAt: null,
      lastRunAt: null,
      busiestDay: null,
    },
    usageCoverage: { runs: 0, runsWithUsage: 0, runsWithoutUsage: 0, ratio: null },
    models: [],
    providers: [],
    tools: [],
    daily: [],
    weekday: [],
    hourly: [],
    coding: {
      runsWithMetrics: 0,
      toolCalls: 0,
      distinctFilesRead: 0,
      redundantReads: 0,
      readsAfterOwnEdit: 0,
      searches: 0,
      searchDumps: 0,
      edits: 0,
      staleEdits: 0,
      exactRepeats: 0,
      failures: 0,
      blocked: 0,
      blindRetries: 0,
      verificationCommands: 0,
      verificationTests: 0,
      runsWithEdits: 0,
      runsVerifiedAfterLastEdit: 0,
      verifiedAfterEditRate: null,
      daily: [],
    },
    ...overrides,
  };
}

test('token counts abbreviate without losing the zero case', () => {
  assert.equal(formatTokens(0), '0');
  assert.equal(formatTokens(412), '412');
  assert.equal(formatTokens(12_300), '12.3K');
  assert.equal(formatTokens(4_500_000), '4.5M');
  assert.equal(formatTokens(null), '—');
});

test('a null rate renders as an em dash, never as zero percent', () => {
  assert.equal(formatRate(null), '—');
  assert.equal(formatRate(undefined), '—');
  assert.equal(formatRate(0), '0%');
  assert.equal(formatRate(0.4237, 1), '42.4%');
});

test('a day with runs but no reported tokens still shows on the heatmap', () => {
  assert.equal(heatLevel(0, 0, 1000), 0, 'nothing ran');
  assert.equal(heatLevel(0, 3, 1000), 1, 'runs happened, the provider just reported nothing');
  assert.equal(heatLevel(200, 1000, 1000), 1);
  assert.equal(heatLevel(400, 1000, 1000), 2);
  assert.equal(heatLevel(600, 1000, 1000), 3);
  assert.equal(heatLevel(900, 1000, 1000), 4);
});

test('daily bars stack output, fresh input and cache read to the day total exactly once', () => {
  const bars = buildDailyTokenBars([
    day('2026-09-14', {
      runs: 2,
      inputTokens: 8_000,
      cachedInputTokens: 6_000,
      freshInputTokens: 2_000,
      outputTokens: 2_000,
      totalTokens: 10_000,
    }),
    day('2026-09-15', { runs: 1, totalTokens: 5_000, outputTokens: 5_000 }),
  ]);

  const first = bars[0];
  assert.deepEqual(
    first.segments.map((segment) => segment.kind),
    ['output', 'freshInput', 'cacheRead'],
  );
  assert.equal(
    first.segments.reduce((sum, segment) => sum + segment.tokens, 0),
    first.total,
    'the segments sum to the day total — cached input is inside input, never beside it',
  );
  assert.equal(first.segments.reduce((sum, segment) => sum + segment.share, 0), 1);
  assert.equal(first.height, 1, 'the tallest day sets the scale');
  assert.equal(bars[1].height, 0.5);
});

test('daily bars drop empty segments and scale a whole empty window to zero', () => {
  const bars = buildDailyTokenBars([day('2026-09-15'), day('2026-09-14')]);
  assert.deepEqual(bars.map((bar) => bar.segments.length), [0, 0]);
  assert.deepEqual(bars.map((bar) => bar.height), [0, 0]);
});

test('the calendar lays days out Monday-first with the leading week padded', () => {
  // 2026-09-15 is a Tuesday, so a window starting there leaves Monday blank.
  const weeks = buildCalendarWeeks([
    day('2026-09-15', { runs: 1, totalTokens: 100 }),
    day('2026-09-16', { runs: 1, totalTokens: 400 }),
  ]);

  assert.equal(weeks.length, 1);
  assert.equal(weeks[0].days.length, 7);
  assert.equal(weeks[0].days[0], null, 'Monday is outside the window');
  assert.equal(weeks[0].days[1]?.date, '2026-09-15');
  assert.equal(weeks[0].days[2]?.date, '2026-09-16');
  assert.equal(weeks[0].days[3], null);
  assert.equal(weeks[0].monthLabel, 'Sep');
  assert.equal(weeks[0].days[2]?.level, 4, 'the busiest day is the darkest cell');
});

test('the calendar is empty for an empty window rather than a single blank column', () => {
  assert.deepEqual(buildCalendarWeeks([]), []);
});

test('weekday and hour charts each scale to their own busiest bucket', () => {
  const weekday: UsageWeekdayRow[] = [0, 1, 2, 3, 4, 5, 6].map((index) => ({
    ...totals({ runs: index === 2 ? 8 : index === 0 ? 4 : 0 }),
    weekday: index,
  }));
  const hourly: UsageHourRow[] = Array.from({ length: 24 }, (_, hour) => ({
    ...totals({ runs: hour === 9 ? 3 : 0 }),
    hour,
  }));

  const rhythm = buildRhythm(weekday, hourly);
  assert.equal(rhythm.weekday[2].label, 'Wed');
  assert.equal(rhythm.weekday[2].share, 1);
  assert.equal(rhythm.weekday[2].peak, true);
  assert.equal(rhythm.weekday[0].share, 0.5);
  assert.equal(rhythm.weekday[1].share, 0);
  assert.equal(rhythm.hourly.length, 24);
  assert.equal(rhythm.hourly[9].label, '9a');
  assert.equal(rhythm.hourly[9].peak, true, 'the hour chart has its own peak, not the weekday one');
  assert.equal(rhythm.hourly[13].label, '1p');
  assert.equal(rhythm.hourly[0].label, '12a');
});

test('the habit trend keeps a null rate on a day with no editing run', () => {
  const trend = buildHabitTrend([
    codingDay('2026-09-14', { runsWithMetrics: 2, runsWithEdits: 2, runsVerifiedAfterLastEdit: 1, verifiedAfterEditRate: 0.5 }),
    codingDay('2026-09-15', { runsWithMetrics: 1, redundantReads: 3 }),
  ]);

  assert.equal(trend[0].verifiedRate, 0.5);
  assert.equal(trend[1].verifiedRate, null, 'a chat-only day did not fail to verify — it had nothing to verify');
  assert.equal(trend[1].redundantReads, 3);
});

test('tiles name their denominator and mark an unknown value as muted', () => {
  const usage = usageFixture({
    totals: {
      ...usageFixture().totals,
      runs: 4,
      runsWithUsage: 2,
      sessions: 2,
      modelCalls: 6,
      inputTokens: 10_000,
      cachedInputTokens: 2_500,
      outputTokens: 1_000,
      totalTokens: 11_000,
      cacheHitRate: 0.25,
      peakInputTokens: 0,
      avgTokensPerRun: 5_500,
    },
    usageCoverage: { runs: 4, runsWithUsage: 2, runsWithoutUsage: 2, ratio: 0.5 },
  });

  const byId = Object.fromEntries(buildUsageTiles(usage).map((tile) => [tile.id, tile]));
  assert.equal(byId.tokens.value, '11.0K');
  assert.match(byId.tokens.detail, /2 of 4 runs reported usage/);
  assert.equal(byId.tokens.tone, 'warning', 'partial coverage is flagged, not silently averaged away');
  assert.equal(byId.cache.value, '25%');
  assert.equal(byId.peak.value, '—');
  assert.equal(byId.peak.tone, 'muted');
  assert.equal(byId.verified.value, '—');
  assert.equal(byId.verified.detail, 'No run edited a file in this window');
  assert.equal(byId.verified.tone, 'muted');
});

test('a cache tile with no reported input tokens says so instead of showing 0%', () => {
  const byId = Object.fromEntries(buildUsageTiles(usageFixture()).map((tile) => [tile.id, tile]));
  assert.equal(byId.cache.value, '—');
  assert.equal(byId.cache.detail, 'No provider reported input tokens');
  assert.equal(byId.cache.tone, 'muted');
});
