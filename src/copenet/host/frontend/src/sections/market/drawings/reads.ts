// What the model is told about the drawings on screen. One row per painted drawing, built
// from the same anchors, bars and scale the canvas uses, so the numbers the model reads and
// the pixels the operator sees are the same fact.
//
// Lines are described in BARS, never in elapsed time: the chart axis is indexed by candle,
// so a weekend is zero distance and any calendar-based slope would bend at every gap. On a
// logarithmic axis a straight line is a constant PERCENT per bar, so the slope column changes
// name (`perBarPct`) rather than silently changing meaning.
import type { ChartObject } from '../chartAgent/types';
import type { Ohlcv } from '../types';
import { futureDrawingTimes } from '../chartDecorations';
import { DRAWING_KINDS, shownOn, type DrawingExtent } from './kinds';

export const FIB_LEVELS = [0, 0.236, 0.382, 0.5, 0.618, 0.786, 1, 1.272, 1.618];
const EXTENT: Partial<Record<ChartObject['kind'], DrawingExtent>> = {
  level: 'both', horizontal_ray: 'right', trendline: 'none', ray: 'right', extended_trendline: 'both',
  channel: 'both', avwap: 'right', measurement: 'none',
};
const COLOR_NAMES: Array<[string, [number, number, number]]> = [
  ['orange', [251, 148, 35]], ['red', [229, 72, 77]], ['green', [105, 197, 137]], ['blue', [59, 158, 255]],
  ['purple', [181, 140, 245]], ['yellow', [242, 201, 76]], ['white', [230, 230, 230]], ['gray', [139, 141, 152]],
];

export interface DrawingRead {
  id: string; kind: ChartObject['kind']; owner: 'you' | 'agent'; color: string; label: string;
  t1: number; p1: number; t2?: number; p2?: number; t3?: number; p3?: number;
  extends?: DrawingExtent; perBar?: number; perBarPct?: number; atLast?: number; vsClosePct?: number; detail?: string;
}

/** The operator says "the red line"; the nearest palette name is what lets the model resolve it. */
export function colorName(hex: string): string {
  // Registry colors are not all six-digit hex; an unparseable one travels as written.
  if (!/^#[0-9a-f]{6}$/i.test(hex)) return hex;
  const value = parseInt(hex.slice(1), 16);
  const rgb = [(value >> 16) & 255, (value >> 8) & 255, value & 255];
  return COLOR_NAMES.map(([name, target]) => ({ name, distance: target.reduce((sum, channel, index) => sum + (channel - rgb[index]) ** 2, 0) }))
    .sort((a, z) => a.distance - z.distance)[0].name;
}

/** A drawing shown on a timeframe it was not placed on has anchors between this chart's
 *  candles. It lands on the candle that contains it: the last one at or before the anchor. */
export function snapToBar(bars: Ohlcv[], time: number): number | null {
  let low = 0;
  let high = bars.length - 1;
  if (high < 0 || time < bars[0].t) return null;
  while (low < high) {
    const middle = (low + high + 1) >> 1;
    if (bars[middle].t <= time) low = middle; else high = middle - 1;
  }
  return bars[low].t;
}

/** Ratio 0 is the first anchor and ratio 1 the second, whichever way the swing was drawn. */
export function fibLevelValues(first: number, second: number): Array<{ ratio: number; value: number }> {
  return FIB_LEVELS.map((ratio) => ({ ratio, value: first + (second - first) * ratio }));
}

export type AvwapSource = 'hlc3' | 'close' | 'hl2' | 'ohlc4';
export const AVWAP_SOURCES: Array<{ value: AvwapSource; label: string }> = [
  { value: 'hlc3', label: '(H + L + C) / 3' }, { value: 'close', label: 'Close' }, { value: 'hl2', label: '(H + L) / 2' }, { value: 'ohlc4', label: '(O + H + L + C) / 4' },
];
export interface AvwapSettings { source: AvwapSource; bandMode: 'stdev' | 'percent'; bands: number[] }

/** What an anchored VWAP computes with. Absent params are the classic study: hlc3, no bands. */
export function avwapSettings(object: ChartObject): AvwapSettings {
  const params = object.params ?? {};
  const source = AVWAP_SOURCES.some((entry) => entry.value === params.source) ? params.source as AvwapSource : 'hlc3';
  const bands = ['band1', 'band2', 'band3'].map((key) => params[key]).filter((value): value is number => typeof value === 'number' && value > 0);
  return { source, bandMode: params.bandMode === 'percent' ? 'percent' : 'stdev', bands };
}

const sourcePrice = (bar: Ohlcv, source: AvwapSource) => source === 'close' ? bar.c : source === 'hl2' ? (bar.h + bar.l) / 2
  : source === 'ohlc4' ? (bar.o + bar.h + bar.l + bar.c) / 4 : (bar.h + bar.l + bar.c) / 3;

/** Cumulative volume-weighted average from the anchor candle forward, with optional bands:
 *  a multiple of the volume-weighted standard deviation, or a fixed percent of the line.
 *  Every series is null before the anchor. */
export function anchoredVwap(object: ChartObject, bars: Ohlcv[]): { values: Array<number | null>; bands: Array<{ multiplier: number; upper: Array<number | null>; lower: Array<number | null> }> } {
  const settings = avwapSettings(object);
  let priceVolume = 0;
  let squareVolume = 0;
  let volume = 0;
  const values: Array<number | null> = [];
  const deviations: Array<number | null> = [];
  for (const bar of bars) {
    if (bar.t < object.anchors[0].t) { values.push(null); deviations.push(null); continue; }
    const price = sourcePrice(bar, settings.source);
    if (bar.v > 0 && Number.isFinite(bar.v)) { priceVolume += price * bar.v; squareVolume += price * price * bar.v; volume += bar.v; }
    const average = volume > 0 ? priceVolume / volume : price;
    values.push(average);
    deviations.push(volume > 0 ? Math.sqrt(Math.max(0, squareVolume / volume - average * average)) : 0);
  }
  const offset = (index: number, multiplier: number) => settings.bandMode === 'percent' ? (values[index] as number) * multiplier / 100 : (deviations[index] as number) * multiplier;
  return { values, bands: settings.bands.map((multiplier) => ({ multiplier,
    upper: values.map((value, index) => value == null ? null : value + offset(index, multiplier)),
    lower: values.map((value, index) => value == null ? null : value - offset(index, multiplier)) })) };
}

export function anchoredVwapValues(object: ChartObject, bars: Ohlcv[]): Array<number | null> { return anchoredVwap(object, bars).values; }

/** The line through two (bar index, price) points, evaluated at another bar index. */
function lineAt(i1: number, p1: number, i2: number, p2: number, index: number, logScale: boolean): number {
  const ratio = (index - i1) / (i2 - i1);
  return logScale ? p1 * (p2 / p1) ** ratio : p1 + (p2 - p1) * ratio;
}

const percent = (value: number, base: number) => base === 0 ? undefined : ((value - base) / base) * 100;

export function readDrawings(objects: ChartObject[], bars: Ohlcv[], options: { timeframe: ChartObject['timeframe']; logScale: boolean }): DrawingRead[] {
  if (!bars.length) return [];
  const index = new Map<number, number>();
  bars.forEach((bar, position) => index.set(bar.t, position));
  futureDrawingTimes(bars).forEach((time, offset) => index.set(time, bars.length + offset));
  const lastIndex = bars.length - 1;
  const close = bars[lastIndex].c;
  const avwapColumns = avwapColumnNames(objects, options.timeframe);

  return objects.filter((object) => object.visible && shownOn(object, options.timeframe)).map((object) => {
    const [a, b, c] = object.anchors;
    const read: DrawingRead = { id: object.id, kind: object.kind, owner: object.owner.kind === 'agent' ? 'agent' : 'you',
      color: colorName(object.color), label: object.label === DRAWING_KINDS[object.kind].label ? '' : object.label, t1: a.t, p1: a.value };
    if (b) { read.t2 = b.t; read.p2 = b.value; }
    if (c) { read.t3 = c.t; read.p3 = c.value; }
    if (EXTENT[object.kind]) read.extends = EXTENT[object.kind];
    const positions = object.anchors.map((anchor) => index.get(anchor.t) ?? (anchor.t <= bars[lastIndex].t ? index.get(snapToBar(bars, anchor.t) ?? -1) : undefined));
    if (positions.some((position) => position === undefined)) { read.detail = 'anchor outside the loaded range; not painted'; return read; }
    const [i1, i2] = positions as number[];
    const against = (value: number) => { read.atLast = value; read.vsClosePct = percent(close, value); };

    switch (object.kind) {
      case 'level': case 'horizontal_ray': against(a.value); break;
      case 'trendline': case 'ray': case 'extended_trendline': case 'channel': {
        if (i1 === i2) break;
        if (options.logScale) read.perBarPct = ((b.value / a.value) ** (1 / (i2 - i1)) - 1) * 100;
        else read.perBar = (b.value - a.value) / (i2 - i1);
        const basis = lineAt(i1, a.value, i2, b.value, lastIndex, options.logScale);
        against(basis);
        if (object.kind === 'channel') {
          const offset = options.logScale ? c.value / lineAt(i1, a.value, i2, b.value, positions[2] as number, true) : c.value - lineAt(i1, a.value, i2, b.value, positions[2] as number, false);
          read.detail = `parallel atLast=${(options.logScale ? basis * offset : basis + offset).toFixed(2)}`;
        }
        break;
      }
      case 'measurement': {
        const change = percent(b.value, a.value);
        read.detail = `${(b.value - a.value).toFixed(2)} (${change === undefined ? 'n/a' : `${change.toFixed(1)}%`}) over ${Math.abs(i2 - i1)} bars`;
        break;
      }
      case 'zone': {
        const low = Math.min(a.value, b.value);
        const high = Math.max(a.value, b.value);
        read.detail = close > high ? 'close above zone' : close < low ? 'close below zone' : 'close inside zone';
        read.vsClosePct = close > high ? percent(close, high) : close < low ? percent(close, low) : 0;
        break;
      }
      case 'fib_retracement':
        read.detail = fibLevelValues(a.value, b.value).map(({ ratio, value }) => `${ratio}=${value.toFixed(2)}`).join('|');
        break;
      case 'position': {
        const reward = Math.abs(b.value - a.value);
        const risk = Math.abs(c.value - a.value);
        read.detail = `${b.value >= a.value ? 'long' : 'short'} entry=p1 target=p2 stop=p3 R:R=${risk === 0 ? 'n/a' : (reward / risk).toFixed(2)}`;
        break;
      }
      case 'avwap': {
        const values = anchoredVwapValues(object, bars);
        const last = values[lastIndex];
        if (last != null) against(last);
        const column = avwapColumns.get(object.id);
        const bands = avwapSettings(object).bands;
        if (column) read.detail = `series in table column ${column}${bands.length ? `; bands x${bands.join('/')} ${avwapSettings(object).bandMode} in avwapUpperN/avwapLowerN` : ''}`;
        break;
      }
      default: break;
    }
    return read;
  });
}

/** AVWAPs that ride the candle matrix as a column. The names mirror the backend's join rule
 *  in `projection._matrix_rows`: the first is `avwap`, later ones carry their resource suffix. */
export const AVWAP_COLUMNS_MAX = 4;
export function avwapColumnNames(objects: ChartObject[], timeframe: ChartObject['timeframe']): Map<string, string> {
  const studies = objects.filter((object) => object.kind === 'avwap' && object.visible && shownOn(object, timeframe)).slice(0, AVWAP_COLUMNS_MAX);
  return new Map(studies.map((object, position) => [object.id, position === 0 ? 'avwap' : `avwap@avwap#${position + 1}`]));
}
