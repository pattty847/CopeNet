// Chart-level style preferences: how the candles, volume and overlays look, and the style a
// new drawing of each kind is born with. Workspace-sticky like the indicator layout, and
// versioned the same way: a blob this build does not understand is discarded, never guessed at.
import { useSyncExternalStore } from 'react';
import type { DrawingKind } from '../chartAgent/types';
import type { LineStyle, StrokeStyle } from './types';

export interface DrawingDefault { color?: string; lineWidth?: number; lineStyle?: LineStyle; fillOpacity?: number }
export interface ChartStyle {
  candles: { up: string; down: string };
  volume: { opacity: number };
  overlay: StrokeStyle;
  comparison: { width: number; style: LineStyle };
  drawingDefaults: Partial<Record<DrawingKind, DrawingDefault>>;
}

export const CHART_STYLE_VERSION = 1;
const STORAGE_KEY = 'mm-chart-style';
export const DEFAULT_CHART_STYLE: ChartStyle = {
  candles: { up: '#69c589', down: '#d96d5f' },
  volume: { opacity: 0.3 },
  overlay: { color: '#8fb8e8', width: 2, style: 'solid' },
  comparison: { width: 2, style: 'solid' },
  drawingDefaults: {},
};

const HEX = /^#[0-9a-fA-F]{6}$/;
const hex = (value: unknown, fallback: string) => typeof value === 'string' && HEX.test(value) ? value : fallback;
const width = (value: unknown, fallback: number) => typeof value === 'number' && [1, 2, 3, 4].includes(value) ? value : fallback;
const style = (value: unknown, fallback: LineStyle): LineStyle => value === 'solid' || value === 'dashed' || value === 'dotted' ? value : fallback;
const unit = (value: unknown, fallback: number, max = 1) => typeof value === 'number' && Number.isFinite(value) ? Math.min(max, Math.max(0, value)) : fallback;

/** localStorage is a trust boundary: every field is checked once here and trusted after. */
export function normalizeChartStyle(raw: unknown): ChartStyle {
  const blob = (raw ?? {}) as Record<string, Record<string, unknown> | undefined>;
  const base = DEFAULT_CHART_STYLE;
  const drawingDefaults: ChartStyle['drawingDefaults'] = {};
  for (const [kind, value] of Object.entries(blob.drawingDefaults ?? {})) {
    const entry = (value ?? {}) as Record<string, unknown>;
    drawingDefaults[kind as DrawingKind] = {
      ...(HEX.test(String(entry.color)) ? { color: String(entry.color) } : {}),
      ...(entry.lineWidth !== undefined ? { lineWidth: width(entry.lineWidth, 1) } : {}),
      ...(entry.lineStyle !== undefined ? { lineStyle: style(entry.lineStyle, 'solid') } : {}),
      ...(entry.fillOpacity !== undefined ? { fillOpacity: unit(entry.fillOpacity, 0.1, 0.6) } : {}),
    };
  }
  return {
    candles: { up: hex(blob.candles?.up, base.candles.up), down: hex(blob.candles?.down, base.candles.down) },
    volume: { opacity: unit(blob.volume?.opacity, base.volume.opacity) },
    overlay: { color: hex(blob.overlay?.color, base.overlay.color), width: width(blob.overlay?.width, base.overlay.width), style: style(blob.overlay?.style, base.overlay.style) },
    comparison: { width: width(blob.comparison?.width, base.comparison.width), style: style(blob.comparison?.style, base.comparison.style) },
    drawingDefaults,
  };
}

function load(): ChartStyle {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? 'null') as { version?: number; style?: unknown } | null;
    return stored?.version === CHART_STYLE_VERSION ? normalizeChartStyle(stored.style) : DEFAULT_CHART_STYLE;
  } catch { return DEFAULT_CHART_STYLE; }
}

let current: ChartStyle | null = null;
const listeners = new Set<() => void>();
export function readChartStyle(): ChartStyle { return current ??= load(); }
export function writeChartStyle(next: ChartStyle): void {
  current = next;
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: CHART_STYLE_VERSION, style: next })); } catch { /* private mode: the preference just does not persist */ }
  listeners.forEach((listener) => listener());
}
export function useChartStyle(): ChartStyle {
  return useSyncExternalStore((listener) => { listeners.add(listener); return () => listeners.delete(listener); }, readChartStyle, readChartStyle);
}
