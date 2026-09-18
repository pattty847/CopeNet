// One registry for what every drawing kind IS. Each form is born from the one before it:
//
//   point     one anchor                      → carries a colour and text
//   line      a point plus a direction        → adds a stroke
//   segment   two points                      → adds an extent (where the stroke stops)
//   area      a segment that encloses space   → adds a fill
//   composite a segment plus a third point    → several lines or areas from one gesture
//   study     a point plus the candle series  → a computed path
//
// A form inherits every settings compartment of the forms above it that apply, so the
// settings toolbar, the gesture (anchor count) and the renderer all read this table and
// never branch on a kind by name. Adding a drawing means adding a row here.
import type { ChartObject, DrawingKind } from '../chartAgent/types';

export type DrawingForm = 'point' | 'line' | 'segment' | 'area' | 'composite' | 'study';
export type LineStyle = 'solid' | 'dashed' | 'dotted';
export interface DrawingKindSpec {
  form: DrawingForm;
  label: string;
  anchors: 1 | 2 | 3;
  /** Settings compartments this kind exposes, in the order the forms introduce them. */
  stroke: boolean;
  fill: boolean;
}

const point = { form: 'point', anchors: 1, stroke: false, fill: false } as const;
const line = { form: 'line', anchors: 1, stroke: true, fill: false } as const;
const segment = { form: 'segment', anchors: 2, stroke: true, fill: false } as const;
const area = { form: 'area', anchors: 2, stroke: true, fill: true } as const;

export const DRAWING_KINDS: Record<DrawingKind, DrawingKindSpec> = {
  label: { ...point, label: 'Note' },
  callout: { ...point, label: 'Callout' },
  level: { ...line, label: 'Price level' },
  horizontal_ray: { ...line, label: 'Horizontal ray' },
  vertical_line: { ...line, label: 'Vertical line' },
  trendline: { ...segment, label: 'Trendline' },
  ray: { ...segment, label: 'Ray' },
  extended_trendline: { ...segment, label: 'Extended trendline' },
  measurement: { ...segment, label: 'Measurement' },
  fib_retracement: { ...segment, label: 'Fibonacci retracement' },
  zone: { ...area, label: 'Price zone' },
  channel: { form: 'composite', label: 'Parallel channel', anchors: 3, stroke: true, fill: false },
  position: { form: 'composite', label: 'Position setup', anchors: 3, stroke: true, fill: true },
  avwap: { form: 'study', label: 'Anchored VWAP', anchors: 1, stroke: true, fill: false },
};

export const DRAWING_COLORS = ['#fb9423', '#e5484d', '#69c589', '#3b9eff', '#b58cf5', '#f2c94c', '#e6e6e6', '#8b8d98'];
export const DEFAULT_DRAWING_COLOR = DRAWING_COLORS[0];
export const LINE_WIDTHS = [1, 2, 3, 4] as const;
export const LINE_STYLES: LineStyle[] = ['solid', 'dashed', 'dotted'];
export const FILL_OPACITIES = [0, 0.1, 0.2, 0.35];

/** Absent style means the default for this owner: the agent's layer dashes, yours is solid. */
export function strokeOf(object: ChartObject): { width: number; style: LineStyle } {
  return { width: object.lineWidth ?? 1, style: object.lineStyle ?? (object.owner.kind === 'agent' ? 'dashed' : 'solid') };
}
export function fillOpacityOf(object: ChartObject): number { return object.fillOpacity ?? 0.1; }
export function lineDash(style: LineStyle): number[] { return style === 'dashed' ? [6, 4] : style === 'dotted' ? [2, 3] : []; }
