// Replay playback state. Owns the cursor, the transport and the clock; owns no data.
//
// The truncation itself happens in the ticker view model, where every derived series
// already lives. This hook only answers "which bar is now".

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  REPLAY_DEFAULT_SPEED,
  replayCursorIndex,
  replayTickMs,
  stepCursorTime,
  stepSpeed,
  type ReplayBar,
  type ReplaySpeed,
} from './chartReplay';

/** Off → arming → active. Arming is its own state rather than a flag on `active` because
 *  nothing is hidden yet while the operator is choosing where to start: the chart still
 *  shows everything, dimmed to the right of the candidate. */
export type ReplayPhase = 'off' | 'arming' | 'active';

export interface ChartReplay {
  phase: ReplayPhase;
  /** Choosing a start point. The chart is NOT truncated yet. */
  arming: boolean;
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
  /** Begin choosing a start point. */
  arm: () => void;
  /** Commit the clicked bar as the start point and begin replaying from it. */
  pick: (time: number) => void;
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
  const [phase, setPhase] = useState<ReplayPhase>('off');
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(REPLAY_DEFAULT_SPEED);
  const [cursorTime, setCursorTime] = useState<number | null>(null);
  const active = phase === 'active';

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

  const arm = useCallback(() => {
    if (bars.length === 0) return;
    setPhase('arming');
    setPlaying(false);
    setCursorTime(null);
  }, [bars.length]);

  /** The clicked time, not the clicked index: the chart hands back a bar timestamp and the
   *  cursor is a timestamp, so nothing has to agree about positions. */
  const pick = useCallback((time: number) => {
    if (bars.length === 0) return;
    setPhase('active');
    setPlaying(false);
    setCursorTime(bars[replayCursorIndex(bars, time)].t);
  }, [bars]);

  const exit = useCallback(() => {
    setPhase('off');
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
    if (phase !== 'off' && bars.length === 0) exit();
  }, [phase, bars.length, exit]);

  return useMemo<ChartReplay>(() => ({
    phase,
    arming: phase === 'arming',
    active,
    playing,
    speed,
    index,
    cursorTime: active ? (bars[index]?.t ?? null) : null,
    total: bars.length,
    atStart,
    atEnd,
    arm,
    pick,
    exit,
    toggle: () => (phase === 'off' ? arm() : exit()),
    play: () => setPlaying(true),
    pause: () => setPlaying(false),
    togglePlay: () => setPlaying((value) => !value),
    step,
    seek,
    toStart: () => seek(0),
    toEnd: () => seek(bars.length - 1),
    setSpeed,
    nudgeSpeed: (delta: number) => setSpeed((current) => stepSpeed(current, delta)),
  }), [phase, active, playing, speed, index, bars, atStart, atEnd, arm, pick, exit, step, seek]);
}
