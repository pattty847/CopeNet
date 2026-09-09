// The replay transport.
//
// A strip under the chart rather than a floating panel over it: the chart already carries
// a legend, cluster boxes, alert lines and a drawing layer, and one more absolutely
// positioned thing competing for the same pixels is how that surface stops being readable.
// It exists only while replay is armed, so it costs nothing the rest of the time.

import { Minus, Pause, Play, Plus, SkipBack, SkipForward, StepBack, StepForward, X } from 'lucide-react';
import { REPLAY_SPEEDS, replayDateLabel, speedLabel } from './chartReplay';
import type { ChartReplay } from './useChartReplay';

export function ReplayBar({ replay }: { replay: ChartReplay }) {
  if (!replay.active || replay.total === 0) return null;
  const position = replay.index + 1;
  const slowest = replay.speed === REPLAY_SPEEDS[0];
  const fastest = replay.speed === REPLAY_SPEEDS[REPLAY_SPEEDS.length - 1];

  return (
    <div className="tw-replay" role="group" aria-label="Chart replay">
      <div className="tw-replay__transport">
        <button type="button" className="tw-iconbtn tw-iconbtn--xs" title="Back to the first bar" aria-label="Back to the first bar" disabled={replay.atStart} onClick={replay.toStart}>
          <SkipBack size={12} />
        </button>
        <button type="button" className="tw-iconbtn tw-iconbtn--xs" title="Previous bar  (←)" aria-label="Previous bar" disabled={replay.atStart} onClick={() => replay.step(-1)}>
          <StepBack size={12} />
        </button>
        <button
          type="button"
          className="tw-iconbtn tw-replay__play"
          data-active={replay.playing}
          title={replay.playing ? 'Pause  (space)' : 'Play  (space)'}
          aria-label={replay.playing ? 'Pause replay' : 'Play replay'}
          disabled={replay.atEnd && !replay.playing}
          onClick={replay.togglePlay}
        >
          {replay.playing ? <Pause size={14} /> : <Play size={14} />}
        </button>
        <button type="button" className="tw-iconbtn tw-iconbtn--xs" title="Next bar  (→)" aria-label="Next bar" disabled={replay.atEnd} onClick={() => replay.step(1)}>
          <StepForward size={12} />
        </button>
        <button type="button" className="tw-iconbtn tw-iconbtn--xs" title="Forward to the last bar" aria-label="Forward to the last bar" disabled={replay.atEnd} onClick={replay.toEnd}>
          <SkipForward size={12} />
        </button>
      </div>

      <span className="tw-sep" />

      <div className="tw-replay__speed">
        <button type="button" className="tw-iconbtn tw-iconbtn--xs" title="Slower" aria-label="Slower" disabled={slowest} onClick={() => replay.nudgeSpeed(-1)}>
          <Minus size={11} />
        </button>
        <span aria-live="off" title="Playback speed">{speedLabel(replay.speed)}</span>
        <button type="button" className="tw-iconbtn tw-iconbtn--xs" title="Faster" aria-label="Faster" disabled={fastest} onClick={() => replay.nudgeSpeed(1)}>
          <Plus size={11} />
        </button>
      </div>

      <span className="tw-sep" />

      <input
        type="range"
        className="tw-replay__scrub"
        min={0}
        max={Math.max(0, replay.total - 1)}
        step={1}
        value={Math.max(0, replay.index)}
        aria-label="Replay position"
        aria-valuetext={`${replayDateLabel(replay.cursorTime)}, bar ${position} of ${replay.total}`}
        onChange={(event) => replay.seek(Number(event.target.value))}
      />

      <span className="tw-replay__stamp">
        {replayDateLabel(replay.cursorTime)}
        <b>{position} / {replay.total}</b>
      </span>

      <button type="button" className="tw-iconbtn tw-iconbtn--xs" title="Exit replay" aria-label="Exit replay" onClick={replay.exit}>
        <X size={12} />
      </button>
    </div>
  );
}
