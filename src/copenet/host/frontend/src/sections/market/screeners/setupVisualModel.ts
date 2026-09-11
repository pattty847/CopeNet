// The setup visual: six months of cached daily closes with the screener's own indicators
// and the rule window drawn as a price zone to the right of the observation, the way the
// Ledger forecast draws reward and risk. Pure geometry over bars; the renderer owns SVG.
//
// Indicators are recomputed here from split-only cached closes, so they can differ slightly
// from TradingView's values, which include the unfinished session. The dock says so.
import { bollingerBands } from '../indicators/calc/bands';
import { relativeStrengthIndex } from '../indicators/calc/momentum';
import { highest, sma } from '../indicators/math';
import type { IndicatorBar, IndicatorSeries } from '../indicators/types';
import type { Candidate, Preset } from './types';
import { ruleWindows } from './ruleWindows';

export const VISIBLE_BARS = 130;
export const VISUAL_HEIGHT = 196;
export const STRIP_HEIGHT = 64;
const LEFT = 8;
const RIGHT = 84;
const TOP = 14;
const BOTTOM = 18;
const LABEL_GAP = 11;

export type ZoneTone = 'up' | 'down' | 'either';
export type SetupOverlay = { key: 'sma50' | 'sma200' | 'high52' | 'bandUpper' | 'bandLower'; path: string };
export type SetupLevel = { y: number; label: string };
export type SetupZone = { top: number; bottom: number; labelTop: string; labelBottom: string; tone: ZoneTone };
export type SetupStrip =
  | { kind: 'rsi'; path: string; windowTop: number | null; windowBottom: number | null; lastY: number; last: number | null; low: number | null; high: number | null }
  | { kind: 'volume'; bars: { x: number; y: number; width: number; height: number; last: boolean }[]; averagePath: string; relativeVolume: number | null };

export type SetupVisualModel = {
  width: number;
  pricePath: string;
  bandPath: string | null;
  overlays: SetupOverlay[];
  zone: SetupZone | null;
  levels: SetupLevel[];
  observedX: number;
  lastY: number;
  startLabel: string;
  observedLabel: string;
  strip: SetupStrip;
};

const dateLabel = (time: number) => new Date(time * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' });
const priceLabel = (value: number) => (value >= 1000 ? value.toLocaleString('en-US', { maximumFractionDigits: 0 }) : value.toFixed(2));
const last = (series: IndicatorSeries) => series[series.length - 1] ?? null;

function overlaysFor(presetId: string): SetupOverlay['key'][] {
  if (presetId === 'compression') return ['bandUpper', 'bandLower', 'high52'];
  if (presetId === 'pullback') return ['sma50', 'sma200', 'high52'];
  if (presetId === 'oversold') return ['sma200', 'high52'];
  if (presetId === 'breakdown') return ['sma50', 'sma200'];
  return ['sma50'];
}

function zoneFor(preset: Preset, sma50: number | null, sma200: number | null, high52: number | null): SetupZone | null {
  const window = (key: string) => ruleWindows(preset).find((rule) => rule.key === key);
  const tone: ZoneTone = preset.direction === 'Bullish' ? 'up' : preset.direction === 'Bearish' ? 'down' : 'either';
  const drawdown = window('drawdown');
  const near50 = window('distance50');
  const under200 = window('distance200');
  if (preset.id === 'compression' && high52 != null && drawdown?.low != null) {
    return { top: high52, bottom: high52 * (1 + drawdown.low / 100), labelTop: '52w high', labelBottom: `${drawdown.low}%`, tone };
  }
  if (preset.id === 'pullback' && sma50 != null && near50?.low != null && near50.high != null) {
    return { top: sma50 * (1 + near50.high / 100), bottom: sma50 * (1 + near50.low / 100), labelTop: `SMA50 +${near50.high}%`, labelBottom: `SMA50 ${near50.low}%`, tone };
  }
  if (preset.id === 'oversold' && high52 != null && drawdown?.low != null && drawdown.high != null) {
    return { top: high52 * (1 + drawdown.high / 100), bottom: high52 * (1 + drawdown.low / 100), labelTop: `${drawdown.high}% of high`, labelBottom: `${drawdown.low}% of high`, tone };
  }
  if (preset.id === 'breakdown' && sma200 != null && under200?.low != null) {
    return { top: sma200, bottom: sma200 * (1 + under200.low / 100), labelTop: 'SMA200', labelBottom: `SMA200 ${under200.low}%`, tone };
  }
  return null;
}

export function setupVisualModel(bars: IndicatorBar[], preset: Preset, row: Candidate, width: number): SetupVisualModel | null {
  if (bars.length < 2) return null;
  const closes = bars.map((bar) => bar.c);
  const full = {
    sma50: sma(closes, 50),
    sma200: sma(closes, 200),
    high52: highest(bars.map((bar) => bar.h), 252),
    rsi: relativeStrengthIndex(bars, 14, 'close'),
    band: bollingerBands(bars, 20, 2, 'close'),
  };
  const start = Math.max(0, bars.length - VISIBLE_BARS);
  const slice = <T>(series: T[]) => series.slice(start);
  const visible = slice(bars);
  const count = visible.length;
  const series: Record<SetupOverlay['key'], IndicatorSeries> = {
    sma50: slice(full.sma50),
    sma200: slice(full.sma200),
    high52: slice(full.high52),
    bandUpper: slice(full.band.upper),
    bandLower: slice(full.band.lower),
  };
  const overlayKeys = overlaysFor(preset.id);
  const zoneAtLast = zoneFor(preset, last(series.sma50), last(series.sma200), last(series.high52));

  const range: number[] = visible.map((bar) => bar.c);
  for (const key of overlayKeys) for (const value of series[key]) if (value != null) range.push(value);
  if (zoneAtLast) range.push(zoneAtLast.top, zoneAtLast.bottom);
  const low = Math.min(...range);
  const high = Math.max(...range);
  const pad = (high - low || 1) * 0.06;
  const plotRight = width - RIGHT;
  const x = (index: number) => LEFT + ((plotRight - LEFT) * index) / Math.max(1, count - 1);
  const y = (value: number) => TOP + (VISUAL_HEIGHT - TOP - BOTTOM) * (1 - (value - (low - pad)) / (high + pad - (low - pad)));
  const path = (values: IndicatorSeries) => {
    let d = '';
    let pen = false;
    values.forEach((value, index) => {
      if (value == null) {
        pen = false;
        return;
      }
      d += `${pen ? 'L' : 'M'}${x(index).toFixed(1)} ${y(value).toFixed(1)}`;
      pen = true;
    });
    return d;
  };
  const observedX = x(count - 1);

  let bandPath: string | null = null;
  if (overlayKeys.includes('bandUpper')) {
    let d = '';
    series.bandUpper.forEach((value, index) => {
      if (value != null) d += `${d ? 'L' : 'M'}${x(index).toFixed(1)} ${y(value).toFixed(1)}`;
    });
    for (let index = count - 1; index >= 0; index -= 1) {
      const value = series.bandLower[index];
      if (value != null) d += `L${x(index).toFixed(1)} ${y(value).toFixed(1)}`;
    }
    bandPath = d ? `${d}Z` : null;
  }

  const zone = zoneAtLast && { ...zoneAtLast, top: y(zoneAtLast.top), bottom: y(zoneAtLast.bottom) };
  // Level labels for overlays the zone does not already name.
  const named = new Set<SetupOverlay['key']>();
  if (preset.id === 'compression' || preset.id === 'oversold') named.add('high52');
  if (preset.id === 'pullback') named.add('sma50');
  if (preset.id === 'breakdown') named.add('sma200');
  const levelText: Record<string, string> = { sma50: 'SMA50', sma200: 'SMA200', high52: '52w hi' };
  const levels: SetupLevel[] = [];
  for (const key of ['sma50', 'sma200', 'high52'] as const) {
    if (!overlayKeys.includes(key) || named.has(key)) continue;
    const value = last(series[key]);
    if (value != null) levels.push({ y: y(value), label: `${levelText[key]} ${priceLabel(value)}` });
  }
  levels.sort((a, b) => a.y - b.y);
  for (let index = 1; index < levels.length; index += 1) {
    if (levels[index].y - levels[index - 1].y < LABEL_GAP) levels[index].y = levels[index - 1].y + LABEL_GAP;
  }

  const strip: SetupStrip = preset.id === 'expansion' ? volumeStrip(visible, x, plotRight, row) : rsiStrip(slice(full.rsi), preset, x);

  return {
    width,
    pricePath: path(visible.map((bar) => bar.c)),
    bandPath,
    overlays: overlayKeys.filter((key) => key !== 'bandUpper' && key !== 'bandLower').map((key) => ({ key, path: path(series[key]) })),
    zone,
    levels,
    observedX,
    lastY: y(visible[count - 1].c),
    startLabel: dateLabel(visible[0].t),
    observedLabel: `Observed ${dateLabel(visible[count - 1].t)}`,
    strip,
  };
}

// The oscillator strip is fitted to what it shows, not to 0–100: the rule window and the
// visible values set the range, so a 40–65 band reads as a band rather than a sliver.
function rsiStrip(values: IndicatorSeries, preset: Preset, x: (index: number) => number): SetupStrip {
  const rule = ruleWindows(preset).find((item) => item.key === 'rsi');
  const present = values.filter((value): value is number => value != null);
  const range = [...present];
  if (rule?.low != null && rule.high != null) range.push(rule.low, rule.high);
  const low = range.length ? Math.min(...range) - 4 : 0;
  const high = range.length ? Math.max(...range) + 4 : 100;
  const top = 6;
  const bottom = 12;
  const y = (value: number) => top + (STRIP_HEIGHT - top - bottom) * (1 - (value - low) / (high - low || 1));
  let path = '';
  let pen = false;
  values.forEach((value, index) => {
    if (value == null) {
      pen = false;
      return;
    }
    path += `${pen ? 'L' : 'M'}${x(index).toFixed(1)} ${y(value).toFixed(1)}`;
    pen = true;
  });
  const lastValue = last(values);
  return {
    kind: 'rsi',
    path,
    windowTop: rule?.high != null ? y(rule.high) : null,
    windowBottom: rule?.low != null ? y(rule.low) : null,
    lastY: lastValue == null ? STRIP_HEIGHT / 2 : y(lastValue),
    last: lastValue,
    low: rule?.low ?? null,
    high: rule?.high ?? null,
  };
}

function volumeStrip(visible: IndicatorBar[], x: (index: number) => number, plotRight: number, row: Candidate): SetupStrip {
  const shown = 40;
  const first = Math.max(0, visible.length - shown);
  const volumes = visible.map((bar) => bar.v);
  const average = sma(volumes, 30);
  const peak = Math.max(1, ...volumes.slice(first));
  const top = 6;
  const bottom = 12;
  const y = (value: number) => top + (STRIP_HEIGHT - top - bottom) * (1 - value / peak);
  const barWidth = (plotRight - LEFT) / shown;
  const bars = [];
  for (let index = first; index < visible.length; index += 1) {
    const height = (STRIP_HEIGHT - top - bottom) * (volumes[index] / peak);
    bars.push({ x: x(index) - barWidth / 2 + 0.5, y: STRIP_HEIGHT - bottom - height, width: Math.max(1, barWidth - 1), height, last: index === visible.length - 1 });
  }
  let averagePath = '';
  for (let index = first; index < visible.length; index += 1) {
    const value = average[index];
    if (value == null) continue;
    averagePath += `${averagePath ? 'L' : 'M'}${x(index).toFixed(1)} ${y(value).toFixed(1)}`;
  }
  return { kind: 'volume', bars, averagePath, relativeVolume: row.relativeVolume };
}
