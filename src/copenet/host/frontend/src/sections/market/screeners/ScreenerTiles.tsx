// The screener strip: one tile per setup, each carrying more than a count — hit rate,
// the ranking metric's distribution across its rule window, the leading sector, and churn
// since the previous observation. Only as many tiles as fit are shown; the rest sit in an
// overflow menu, and the active setup is always one of the visible ones.
import { useEffect, useRef, useState } from 'react';
import type { Preset, ScreenerRun } from './types';
import type { ScreenChurn } from './churn';
import { ruleWindows } from './ruleWindows';
import { metricHistogram, summarizeScreen } from './screenSummary';

const TILE_WIDTH = 176;
const DIRECTION_GLYPH: Record<string, string> = { Bullish: '↑', Bearish: '↓', Either: '↕' };

export function ScreenerTiles({
  presets,
  run,
  active,
  churn,
  onSelect,
}: {
  presets: Preset[];
  run: ScreenerRun | null;
  active: string;
  churn: Record<string, ScreenChurn> | null;
  onSelect: (id: string) => void;
}) {
  const strip = useRef<HTMLElement>(null);
  const [capacity, setCapacity] = useState(presets.length);
  useEffect(() => {
    const element = strip.current;
    if (!element) return;
    const measure = () => setCapacity(Math.max(2, Math.floor(element.clientWidth / TILE_WIDTH)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const overflowing = presets.length > capacity;
  const slots = overflowing ? capacity - 1 : presets.length;
  let visible = presets.slice(0, slots);
  let hidden = presets.slice(slots);
  if (overflowing && !visible.some((preset) => preset.id === active)) {
    const current = presets.find((preset) => preset.id === active);
    if (current) {
      visible = [...visible.slice(0, -1), current];
      hidden = presets.filter((preset) => !visible.includes(preset));
    }
  }
  return (
    <nav ref={strip} className="scr-tiles" aria-label="Screener setups">
      {visible.map((preset) => {
        const screen = run?.screens.find((item) => item.id === preset.id);
        const summary = screen && run ? summarizeScreen(screen.rows, run.eligible) : null;
        const rule = ruleWindows(preset).find((item) => item.key === preset.metric);
        const bins = screen && rule ? metricHistogram(screen.rows, rule) : [];
        const peak = Math.max(1, ...bins);
        const hot = preset.ascending ? 0 : bins.length - 1;
        const change = churn?.[preset.id];
        const lead = summary?.sectors[0];
        const count = screen ? screen.rows.length : '—';
        return (
          <button
            key={preset.id}
            type="button"
            className="scr-tile"
            aria-pressed={preset.id === active}
            aria-label={`${preset.name} ${preset.direction} ${count}`}
            onClick={() => onSelect(preset.id)}
          >
            <span className="scr-tile__name">{preset.name}</span>
            <span className="scr-tile__direction" data-direction={preset.direction}>
              {DIRECTION_GLYPH[preset.direction] ?? ''} {preset.direction}
            </span>
            <span className="scr-tile__count">
              <b>{count}</b>
              {summary && <span>{(summary.hitRate * 100).toFixed(1)}% of eligible</span>}
            </span>
            {bins.length > 0 && rule && (
              <span className="scr-tile__hist" title={`Distribution of ${rule.label.toLowerCase()} across the rule window`}>
                {bins.map((value, index) => (
                  <i key={index} data-hot={index === hot} style={{ height: `${Math.max(1, Math.round((value / peak) * 16))}px` }} />
                ))}
              </span>
            )}
            <span className="scr-tile__meta">
              <span>{lead && summary ? `${lead.name} ${Math.round((lead.count / summary.count) * 100)}%` : ''}</span>
              <span>
                {change ? (
                  <>
                    <b>+{change.added.size}</b> new · <b>−{change.dropped}</b> gone
                  </>
                ) : (
                  ''
                )}
              </span>
            </span>
          </button>
        );
      })}
      {hidden.length > 0 && (
        <label className="scr-tile scr-tile--more">
          <span className="scr-tile__name">{hidden.length} more</span>
          <select value="" onChange={(event) => event.target.value && onSelect(event.target.value)} aria-label="More screener setups">
            <option value="">Choose…</option>
            {hidden.map((preset) => (
              <option key={preset.id} value={preset.id}>
                {preset.name} · {run?.screens.find((item) => item.id === preset.id)?.rows.length ?? '—'}
              </option>
            ))}
          </select>
        </label>
      )}
    </nav>
  );
}
