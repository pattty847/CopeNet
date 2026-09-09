// Replay playback state. Owns the cursor, the transport and the clock; owns no data.
//
// The truncation itself happens in the ticker view model, where every derived series
// already lives. This hook only answers "which bar is now".

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  REPLAY_DEFAULT_SPEED,
  hiddenBarTimes,
  replayCursorIndex,
  replayTickMs,
  stepCursorTime,
  stepSpeed,
  type ReplayBar,
  type ReplaySpeed,
} from './chartReplay';

export interface ChartReplay {
  active: boolean;
  playing: boolean;
  speed: ReplaySpeed;
  /** Index into the bars this replay was given. -1 when there are none. */
  index: number;
  /** Timestamp of the bar under the cursor, or null when replay is off. */
  cursorTime: number | null;
  total: number;
  atStart: boolean;
  atEnd: boolean;
  enter: () => void;
  exit: () => void;
  toggle: () => void;
  play: () => void;
  pause: () => void;
  togglePlay: () => void;
  step: (delta: number) => void;
  seek: (index: number) => void;
  toStart: () => void;
  toEnd: () => void;
  setSpeed: (speed: ReplaySpeed) => void;
  nudgeSpeed: (delta: number) => void;
}

export function useChartReplay(bars: readonly ReplayBar[]): ChartReplay {
  const [active, setActive] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(REPLAY_DEFAULT_SPEED);
  const [cursorTime, setCursorTime] = useState<number | null>(null);

  const index = active ? replayCursorIndex(bars, cursorTime) : bars.length - 1;
  const atEnd = index >= bars.length - 1;
  const atStart = index <= 0;

  const seek = useCallback((next: number) => {
    const bar = bars[Math.min(bars.length - 1, Math.max(0, next))];
    if (bar) setCursorTime(bar.t);
  }, [bars]);

  const step = useCallback((delta: number) => {
    const next = stepCursorTime(bars, index, delta);
    if (next != null) setCursorTime(next);
  }, [bars, index]);

  const enter = useCallback(() => {
    if (bars.length === 0) return;
    setActive(true);
    setPlaying(false);
    // From the left edge of the visible range: replay walks the window you chose. Indicators
    // are still warm here, because they compute over the full loaded history behind it.
    setCursorTime(bars[0].t);
  }, [bars]);

  const exit = useCallback(() => {
    setActive(false);
    setPlaying(false);
    setCursorTime(null);
  }, []);

  // Playback stops at the last bar rather than wrapping: a replay that silently restarted
  // would show old bars while the transport still read "playing".
  useEffect(() => {
    if (!active || !playing) return;
    if (atEnd) {
      setPlaying(false);
      return;
    }
    const timer = window.setInterval(() => {
      setCursorTime((current) => {
        const at = replayCursorIndex(bars, current);
        return stepCursorTime(bars, at, 1) ?? current;
      });
    }, replayTickMs(speed));
    return () => window.clearInterval(timer);
  }, [active, playing, speed, atEnd, bars]);

  // Nothing left to replay — an emptied series must not leave the transport armed over it.
  useEffect(() => {
    if (active && bars.length === 0) exit();
  }, [active, bars.length, exit]);

  return useMemo<ChartReplay>(() => ({
    active,
    playing,
    speed,
    index,
    cursorTime: active ? (bars[index]?.t ?? null) : null,
    total: bars.length,
    atStart,
    atEnd,
    enter,
    exit,
    toggle: () => (active ? exit() : enter()),
    play: () => setPlaying(true),
    pause: () => setPlaying(false),
    togglePlay: () => setPlaying((value) => !value),
    step,
    seek,
    toStart: () => seek(0),
    toEnd: () => seek(bars.length - 1),
    setSpeed,
    nudgeSpeed: (delta: number) => setSpeed((current) => stepSpeed(current, delta)),
  }), [active, playing, speed, index, bars, atStart, atEnd, enter, exit, step, seek]);
}

/** Timestamps the replay is holding back, for the chart's whitespace padding. */
export function useReplayTrailingTimes(bars: readonly ReplayBar[], replay: ChartReplay): number[] {
  const { active, index } = replay;
  const empty = useRef<number[]>([]).current;
  return useMemo(() => (active ? hiddenBarTimes(bars, index) : empty), [active, bars, index, empty]);
}
