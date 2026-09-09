import assert from 'node:assert/strict';
import test from 'node:test';

import {
  REPLAY_MIN_INTERVAL_MS,
  REPLAY_SPEEDS,
  REPLAY_MIN_SPAN_BARS,
  REPLAY_RIGHT_PAD_BARS,
  replayCursorIndex,
  replayEntryRange,
  replayDateLabel,
  replayTickMs,
  speedLabel,
  stepCursorTime,
  stepSpeed,
} from '../src/sections/market/replay/chartReplay';

const bars = [100, 200, 300, 400, 500].map((t) => ({ t }));

test('the cursor is a time, so it survives a re-slice at a different interval', () => {
  assert.equal(replayCursorIndex(bars, 300), 2);
  // A weekly bar opening before the daily cursor still resolves to the bar containing it.
  assert.equal(replayCursorIndex(bars, 349), 2);
  assert.equal(replayCursorIndex(bars, 500), 4);
});

test('a cursor outside the series resolves to a bar rather than to nothing', () => {
  // Shortening the range drops the bars the cursor pointed at. Showing the first bar is a
  // recoverable state; showing an empty chart reads as a broken one.
  assert.equal(replayCursorIndex(bars, 1), 0);
  assert.equal(replayCursorIndex(bars, 9999), 4);
  assert.equal(replayCursorIndex([], 300), -1);
  // No cursor at all means live: the last bar.
  assert.equal(replayCursorIndex(bars, null), 4);
});

test('stepping clamps at both ends and reports when there is nowhere to go', () => {
  assert.equal(stepCursorTime(bars, 0, 1), 200);
  assert.equal(stepCursorTime(bars, 2, -1), 200);
  assert.equal(stepCursorTime(bars, 4, 1), null, 'playback must stop at the last bar, never wrap');
  assert.equal(stepCursorTime(bars, 0, -1), null);
  assert.equal(stepCursorTime([], 0, 1), null);
});

test('replay opens framed on the revealed history with headroom on the right', () => {
  const range = replayEntryRange(104);
  assert.equal(range.to, 103 + REPLAY_RIGHT_PAD_BARS, 'the newest bar sits a few bars off the right edge');
  assert.equal(range.from, -1, 'and the whole revealed prefix is in frame');
});

test('a start point only a few bars in still opens at a readable width', () => {
  // Fitting three candles across the chart is technically a fit and useless to look at.
  const range = replayEntryRange(3);
  assert.equal(range.to - range.from, REPLAY_MIN_SPAN_BARS);
  assert.equal(range.to, 2 + REPLAY_RIGHT_PAD_BARS);
});

test('speed steps through the presets and clamps at both ends', () => {
  assert.equal(stepSpeed(1, 1), 2);
  assert.equal(stepSpeed(1, -1), 0.5);
  assert.equal(stepSpeed(0.25, -1), 0.25);
  assert.equal(stepSpeed(16, 1), 16);
  assert.equal(speedLabel(0.5), '.5×');
  assert.equal(speedLabel(4), '4×');
});

test('tick interval shortens with speed and never goes below the floor', () => {
  assert.equal(replayTickMs(1), 700);
  assert.equal(replayTickMs(2), 350);
  assert.equal(replayTickMs(0.5), 1400);
  // The floor does not bite at any shipped preset; it exists so adding a faster one cannot
  // schedule a tick the browser has no frame for.
  assert.equal(replayTickMs(16), 44);
  assert.ok(REPLAY_SPEEDS.every((speed) => replayTickMs(speed) >= REPLAY_MIN_INTERVAL_MS));
});

test('the cursor stamp reads in UTC, like every other bar date on the chart', () => {
  assert.equal(replayDateLabel(null), '—');
  assert.match(replayDateLabel(Date.UTC(2024, 2, 15) / 1000), /Mar 15, 2024/);
});
