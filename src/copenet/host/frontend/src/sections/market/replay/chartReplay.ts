// Chart replay: the pure model.
//
// Replay is a CURSOR IN TIME, never an index. An index would be silently wrong the moment
// the operator switched interval or range underneath it — 260 weekly bars and 1250 daily
// bars do not share position 140, so a stored index would land the replay on a different
// date and nothing on screen would say so. A timestamp survives every re-slice: the cursor
// resolves to the last bar at or before it, whatever the bars now are.
//
// Everything here is pure so the playback rules can be tested without a chart or a clock.

export const REPLAY_SPEEDS = [0.25, 0.5, 1, 2, 4, 8, 16] as const;
export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number];

export const REPLAY_DEFAULT_SPEED: ReplaySpeed = 1;
/** One bar per this many milliseconds at 1×. */
export const REPLAY_BASE_INTERVAL_MS = 700;
/** Below this the browser cannot keep up with a full re-slice per tick anyway. */
export const REPLAY_MIN_INTERVAL_MS = 40;

/** Bars of headroom kept to the right of the newest revealed candle, so the next one arrives
 *  into visible space instead of appearing under the price axis. */
export const REPLAY_RIGHT_PAD_BARS = 4;

/** Floor on the entry framing. Starting three bars in would otherwise fit three candles
 *  across the whole chart. */
export const REPLAY_MIN_SPAN_BARS = 24;

/** What the chart needs to know about replay. Charts with no replay omit it entirely. */
export interface ChartReplayBinding {
  /** Bars are truncated at the cursor and the chart must stop auto-fitting. */
  active: boolean;
  /** Picking a start point: the chart dims the future and takes the next click. */
  arming: boolean;
  onPick: (time: number) => void;
}

export interface ReplayBar {
  t: number;
}

export function replayTickMs(speed: ReplaySpeed): number {
  return Math.max(REPLAY_MIN_INTERVAL_MS, Math.round(REPLAY_BASE_INTERVAL_MS / speed));
}

export function stepSpeed(speed: ReplaySpeed, delta: number): ReplaySpeed {
  const at = REPLAY_SPEEDS.indexOf(speed);
  const next = Math.min(REPLAY_SPEEDS.length - 1, Math.max(0, (at < 0 ? REPLAY_SPEEDS.indexOf(REPLAY_DEFAULT_SPEED) : at) + delta));
  return REPLAY_SPEEDS[next];
}

export function speedLabel(speed: ReplaySpeed): string {
  return `${speed < 1 ? speed.toString().replace(/^0/, '') : speed}×`;
}

/** Index of the last bar at or before `cursorTime`, clamped into the array.
 *
 *  Returns -1 only for an empty series. A cursor that predates the first bar — which is
 *  what a range change to a shorter window produces — resolves to bar 0 rather than to
 *  "no bars", because a replay showing nothing at all reads as a broken chart. */
export function replayCursorIndex(bars: readonly ReplayBar[], cursorTime: number | null): number {
  if (bars.length === 0) return -1;
  if (cursorTime == null) return bars.length - 1;
  let low = 0;
  let high = bars.length - 1;
  let found = -1;
  while (low <= high) {
    const mid = (low + high) >> 1;
    if (bars[mid].t <= cursorTime) {
      found = mid;
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return found < 0 ? 0 : found;
}

/** The cursor time for `index + delta`, clamped to the series. Null when there is nothing
 *  to move to, which is how the caller knows playback has run out of bars. */
export function stepCursorTime(bars: readonly ReplayBar[], index: number, delta: number): number | null {
  if (bars.length === 0) return null;
  const next = index + delta;
  if (next < 0 || next > bars.length - 1) return null;
  return bars[next].t;
}

/** The logical range that frames a replay as it opens: every revealed bar, plus headroom.
 *
 *  This is computed ONCE, when replay starts. From then on the chart's framing belongs to
 *  the operator — every step shifts their range by the bars revealed rather than refitting,
 *  so the newest candle holds its position, history slides left underneath it, and whatever
 *  zoom they set survives. */
export function replayEntryRange(revealedBars: number): { from: number; to: number } {
  const to = revealedBars - 1 + REPLAY_RIGHT_PAD_BARS;
  const span = Math.max(revealedBars + REPLAY_RIGHT_PAD_BARS, REPLAY_MIN_SPAN_BARS);
  return { from: to - span, to };
}

const CURSOR_DATE = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: 'numeric',
  timeZone: 'UTC',
});

export function replayDateLabel(time: number | null): string {
  return time == null ? '—' : CURSOR_DATE.format(new Date(time * 1000));
}
