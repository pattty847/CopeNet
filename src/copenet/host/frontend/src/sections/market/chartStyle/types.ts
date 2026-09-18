// The shared vocabulary for how anything on the chart LOOKS, and the descriptor a painted
// thing hands to the settings popup. A thing's menu is the compartments it is built from
// (each form is born from the one before it: a stroke, then a fill, then text) plus one
// `own` compartment for what only it has. The popup and the selection bar render whatever
// descriptor they are given; they never learn what a trendline or an SMA is. Storage stays
// with each source, so an adapter writes to its own store.
import type { ReactNode } from 'react';

export type LineStyle = 'solid' | 'dashed' | 'dotted';
export interface StrokeStyle { color: string; width: number; style: LineStyle }
export interface FillStyle { color: string; opacity: number }

export const STYLE_COLORS = ['#fb9423', '#e5484d', '#69c589', '#3b9eff', '#b58cf5', '#f2c94c', '#e6e6e6', '#8b8d98'];
export const LINE_WIDTHS = [1, 2, 3, 4] as const;
export const LINE_STYLES: LineStyle[] = ['solid', 'dashed', 'dotted'];
export function lineDash(style: LineStyle): number[] { return style === 'dashed' ? [6, 4] : style === 'dotted' ? [2, 3] : []; }

export interface StrokeField {
  key: string;
  label: string;
  value: StrokeStyle;
  onChange: (next: Partial<StrokeStyle>) => void;
  /** Present when this stroke can be switched off on its own: one output of an indicator. */
  visible?: { value: boolean; onChange: (next: boolean) => void };
  /** Some strokes only take a color (a candle body). */
  colorOnly?: boolean;
}
export interface FillField { key: string; label: string; value: FillStyle; onChange: (next: Partial<FillStyle>) => void; opacityOnly?: boolean }
export interface ChoiceField { key: string; label: string; value: string; choices: Array<{ value: string; label: string }>; onChange: (next: string) => void }
export interface ToggleField { key: string; label: string; value: boolean; onChange: (next: boolean) => void }
export interface AnchorField { key: string; label: string; time: number; price: number; onChange: (next: { time?: number; price?: number }) => void }

export interface Styleable {
  id: string;
  title: string;
  /** Inputs tab: what this thing computes, or for an agent drawing the evidence behind it. */
  own?: ReactNode;
  ownLabel?: string;
  /** Style tab. */
  strokes: StrokeField[];
  fills: FillField[];
  choices?: ChoiceField[];
  toggles?: ToggleField[];
  /** Text tab. */
  text?: { value: string; onChange: (next: string) => void };
  /** Coordinates tab. */
  anchors?: { fields: AnchorField[]; times: number[] };
  /** Visibility tab. */
  visibility?: ToggleField[];
  actions: {
    hide?: () => void;
    remove?: () => void;
    lock?: { value: boolean; toggle: () => void };
    saveAsDefault?: () => void;
    resetToDefault?: () => void;
  };
  /** The popup edits a draft. Ok keeps it as ONE change; Cancel leaves the thing untouched. */
  commit: () => void;
  cancel: () => void;
}
