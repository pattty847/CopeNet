// The chart's own series, described to the shared settings surfaces: candles, volume, the
// financial overlay and comparison lines. Their style is a workspace preference
// (`store.ts`), applied live, so Cancel restores the snapshot taken when the popup opened.
import { useMemo, useState } from 'react';
import { ChartObjectSettings } from './ChartObjectSettings';
import type { SelectionBarModel } from './SelectionBar';
import { DEFAULT_CHART_STYLE, useChartStyle, writeChartStyle, type ChartStyle } from './store';
import type { Styleable } from './types';

export type ChartSeriesId = 'candles' | 'volume' | 'overlay' | 'comparison';
const TITLES: Record<ChartSeriesId, string> = { candles: 'Candles', volume: 'Volume', overlay: 'Financial overlay', comparison: 'Comparison lines' };

function parts(id: ChartSeriesId, style: ChartStyle, overlayLabel?: string): Pick<Styleable, 'strokes' | 'fills' | 'title'> {
  const set = (next: Partial<ChartStyle>) => writeChartStyle({ ...style, ...next });
  if (id === 'candles') return { title: TITLES.candles, fills: [], strokes: [
    { key: 'up', label: 'Up candles', colorOnly: true, value: { color: style.candles.up, width: 1, style: 'solid' }, onChange: (next) => { if (next.color) set({ candles: { ...style.candles, up: next.color } }); } },
    { key: 'down', label: 'Down candles', colorOnly: true, value: { color: style.candles.down, width: 1, style: 'solid' }, onChange: (next) => { if (next.color) set({ candles: { ...style.candles, down: next.color } }); } },
  ] };
  if (id === 'volume') return { title: TITLES.volume, strokes: [], fills: [
    { key: 'volume', label: 'Bars (colored by the candle)', opacityOnly: true, value: { color: style.candles.up, opacity: style.volume.opacity }, onChange: (next) => { if (next.opacity !== undefined) set({ volume: { opacity: next.opacity } }); } },
  ] };
  if (id === 'overlay') return { title: overlayLabel ?? TITLES.overlay, fills: [], strokes: [
    { key: 'overlay', label: 'Line', value: style.overlay, onChange: (next) => set({ overlay: { ...style.overlay, ...next } }) },
  ] };
  return { title: TITLES.comparison, fills: [], strokes: [
    { key: 'comparison', label: 'Lines (each keeps its own color)', value: { color: '#8b8d98', ...style.comparison }, onChange: (next) => set({ comparison: { width: next.width ?? style.comparison.width, style: next.style ?? style.comparison.style } }) },
  ] };
}

export function seriesBarModel(id: ChartSeriesId, style: ChartStyle, overlayLabel: string | undefined, handlers: { openSettings: () => void; deselect: () => void }): SelectionBarModel {
  const described = parts(id, style, overlayLabel);
  return { id: `series:${id}`, title: described.title, stroke: id === 'comparison' ? undefined : described.strokes[0], fill: described.fills[0], ...handlers };
}

export function SeriesSettings({ id, overlayLabel, onClose }: { id: ChartSeriesId; overlayLabel?: string; onClose: () => void }) {
  const style = useChartStyle();
  const [snapshot] = useState(style);
  const target = useMemo<Styleable>(() => ({
    id: `series:${id}`, ...parts(id, style, overlayLabel),
    actions: { resetToDefault: () => writeChartStyle({ ...style, ...(id === 'candles' ? { candles: DEFAULT_CHART_STYLE.candles } : id === 'volume' ? { volume: DEFAULT_CHART_STYLE.volume }
      : id === 'overlay' ? { overlay: DEFAULT_CHART_STYLE.overlay } : { comparison: DEFAULT_CHART_STYLE.comparison }) }) },
    commit: () => undefined,
    cancel: () => writeChartStyle(snapshot),
  }), [id, style, overlayLabel, snapshot]);
  return <ChartObjectSettings target={target} onClose={onClose} />;
}
