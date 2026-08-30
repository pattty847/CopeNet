// The indicator registry contract.
//
// ONE registry entry is enough to populate the picker, the settings form, the legend, the
// persisted layout and the renderer. Nothing about an indicator is declared twice, and
// nothing about an indicator lives in a component — adding EMA and adding MAMA touch the
// same single file and no others.
//
// The hard boundary this file draws: `compute` is PURE. It takes bars and a config, returns
// numbers, and knows nothing about React or Lightweight Charts. Everything chart-shaped
// (series, panes, colours, lifecycles) is declared as data here and interpreted by
// `render.ts`. That is what keeps 27 indicators from becoming 27 special cases in the chart
// component.

/** Which field of a bar an indicator reads. Derived sources are computed, never stored. */
export type IndicatorSource = 'open' | 'high' | 'low' | 'close' | 'hl2' | 'hlc3' | 'ohlc4';

export const INDICATOR_SOURCES: { value: IndicatorSource; label: string }[] = [
  { value: 'close', label: 'Close' },
  { value: 'open', label: 'Open' },
  { value: 'high', label: 'High' },
  { value: 'low', label: 'Low' },
  { value: 'hl2', label: 'HL2' },
  { value: 'hlc3', label: 'HLC3' },
  { value: 'ohlc4', label: 'OHLC4' },
];

/** The OHLCV shape the calculations consume. Deliberately structural rather than an import
 *  of the market `Ohlcv` type, so `calc/` stays free of product coupling. */
export interface IndicatorBar {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export type IndicatorField = 'open' | 'high' | 'low' | 'close' | 'volume';

export type IndicatorCategory = 'trend' | 'momentum' | 'volatility' | 'volume' | 'ehlers';

export const INDICATOR_CATEGORIES: { key: IndicatorCategory; label: string }[] = [
  { key: 'trend', label: 'Trend & overlays' },
  { key: 'momentum', label: 'Momentum' },
  { key: 'volatility', label: 'Volatility' },
  { key: 'volume', label: 'Volume' },
  { key: 'ehlers', label: 'Ehlers' },
];

export type IndicatorConfigValue = number | string | boolean;
export type IndicatorConfig = Record<string, IndicatorConfigValue>;

/** An input is the whole spec for one settings control: label, default, bounds and whether it
 *  is common enough to show without opening the advanced disclosure. */
export type IndicatorInput =
  | { kind: 'number'; key: string; label: string; default: number; min: number; max: number; step: number; advanced?: boolean }
  | { kind: 'source'; key: string; label: string; default: IndicatorSource; advanced?: boolean }
  | { kind: 'enum'; key: string; label: string; default: string; choices: { value: string; label: string }[]; advanced?: boolean }
  | { kind: 'boolean'; key: string; label: string; default: boolean; advanced?: boolean };

export type IndicatorPlot = 'line' | 'stepline' | 'histogram' | 'area';

/** One drawable series produced by an indicator. `band` marks the two edges of a channel so
 *  the renderer can draw them alike without the definition repeating itself. */
export interface IndicatorOutput {
  key: string;
  label: string;
  plot: IndicatorPlot;
  color: string;
  lineWidth?: 1 | 2 | 3 | 4;
  lineStyle?: 'solid' | 'dashed' | 'dotted';
  /** Hidden by default but still computed — MACD's zero line, a band's midline. */
  hiddenByDefault?: boolean;
  /** Decimal places for the legend value. Defaults to the pane's own inference. */
  precision?: number;
}

/** A static horizontal line: RSI 70/30, CCI ±100, the MACD/CMF zero. Reference lines are
 *  declared, never drawn by hand, so every bounded oscillator gets them for free. */
export interface IndicatorReference {
  value: number;
  label?: string;
  color?: string;
  lineStyle?: 'solid' | 'dashed' | 'dotted';
}

/** Everything compute needs that is not a bar. `barsPerYear` lets Historical Volatility
 *  annualise honestly against the chart's actual interval instead of assuming daily. */
export interface IndicatorContext {
  barsPerYear: number;
}

/** Output values aligned 1:1 with the input bars. `null` means "not computable here" —
 *  warm-up, a zero denominator, or missing volume. Never NaN, never Infinity. */
export type IndicatorSeries = (number | null)[];

export interface IndicatorResult {
  values: Record<string, IndicatorSeries>;
  /** Optional per-bar colour override, for series whose meaning flips (Supertrend's
   *  direction, MACD's histogram sign). Keyed by output key. */
  colors?: Record<string, (string | null)[]>;
}

export interface IndicatorDefinition {
  /** Stable across releases: it is the persistence key. Renaming one orphans saved layouts. */
  id: string;
  name: string;
  category: IndicatorCategory;
  /** Only where the name does not carry it. Discovery aid in the picker, not documentation. */
  description?: string;
  /** `price` overlays the candle pane and shares its scale; `pane` gets its own stacked pane. */
  placement: 'price' | 'pane';
  requires: IndicatorField[];
  inputs: IndicatorInput[];
  outputs: IndicatorOutput[];
  references?: IndicatorReference[];
  /** Fixed pane bounds for a bounded oscillator, so RSI does not autoscale to its own noise. */
  paneRange?: { min?: number; max?: number };
  /** Bars consumed before the first non-null output. Drives the "needs N bars" notice. */
  warmup: (config: IndicatorConfig) => number;
  compute: (bars: IndicatorBar[], config: IndicatorConfig, context: IndicatorContext) => IndicatorResult;
  /** Legend label for a configured instance, e.g. "EMA 20" or "MACD 12/26/9". */
  short: (config: IndicatorConfig) => string;
  /** Legend value formatter. Defaults to a magnitude-aware fixed-decimal format. */
  format?: (value: number, config: IndicatorConfig) => string;
}
