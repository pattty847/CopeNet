// What the Signals numbers mean, in words.
//
// Every screen row used to render bare numbers — "0.86", "RSI 30", "-48.0% dd" — and a `why`
// that was actually the trend note, identical on every row. The numbers were honest and
// unreadable: nothing on the page said what a score of 0.86 was out of, which of the four
// accumulation conditions had fired, or whether RSI 30 was the interesting end of the range.
//
// These are pure interpretation of values the backend already computes. No new claims: a band
// label is a restatement of a threshold, never a forecast.

import type { ConfluenceFactor, ScreenCalibration } from './types';

/** The four accumulation conditions, mirroring `signals.CONFLUENCE_FACTORS`. */
export const CONFLUENCE_LABELS: Record<ConfluenceFactor, { label: string; rule: string }> = {
  extended_below_ma: { label: 'below 40W', rule: 'price is 3% or more under its 40-week average' },
  deep_drawdown: { label: 'deep drawdown', rule: 'down 20% or more from its high' },
  rsi_oversold: { label: 'oversold', rule: 'weekly RSI at or below 40' },
  reclaimed_10w: { label: 'reclaimed 10W', rule: 'crossed back above its 10-week average this week' },
};

/** The seven pre-registered bottoming tests, mirroring `features.SB_TESTS`. */
export const SB_TEST_LABELS: Record<string, string> = {
  sb_lower_lows_stopped: 'lower lows stopped',
  sb_higher_low: 'higher low',
  sb_ma_reclaim: 'reclaimed 10W',
  sb_drawdown_stabilized: 'drawdown stabilized',
  sb_rs_improving: 'outperforming again',
  sb_volume_drying: 'selling drying up',
  sb_momentum_divergence: 'momentum divergence',
};

export interface Band {
  word: string;
  /** 'notable' marks the end of the range the screen is actually hunting in. */
  notable: boolean;
}

/** Parse a formatted percent like "-48.0%" or "+8.3%". */
export function parsePct(value: string): number | null {
  const parsed = Number.parseFloat(value.replace(/[^0-9.+-]/g, ''));
  return Number.isFinite(parsed) ? parsed : null;
}

export function rsiBand(value: string): Band | null {
  const rsi = Number.parseFloat(value);
  if (!Number.isFinite(rsi)) return null;
  if (rsi <= 30) return { word: 'oversold', notable: true };
  if (rsi <= 40) return { word: 'weak', notable: true };
  if (rsi < 60) return { word: 'neutral', notable: false };
  if (rsi < 70) return { word: 'firm', notable: false };
  return { word: 'overbought', notable: true };
}

export function drawdownBand(value: string): Band | null {
  const pct = parsePct(value);
  if (pct === null) return null;
  if (pct > -10) return { word: 'shallow', notable: false };
  if (pct > -25) return { word: 'correction', notable: false };
  if (pct > -50) return { word: 'deep', notable: true };
  return { word: 'severe', notable: true };
}

/** "8w" / "1y 4w" — a trend's age, from the weekly bar count. */
export function trendAge(weeks: number): string {
  if (!Number.isFinite(weeks) || weeks <= 0) return 'new';
  if (weeks < 52) return `${weeks}w`;
  const years = Math.floor(weeks / 52);
  const rest = weeks % 52;
  return rest ? `${years}y ${rest}w` : `${years}y`;
}

/** The one sentence a calibration is actually saying. Deliberately unflattering: a hit rate
 *  near 50% is a coin flip and the copy says so. */
export function calibrationRead(rate: ScreenCalibration): string {
  if (rate.n < 30) return `Only ${rate.n} historical cases — too thin to lean on.`;
  const edge =
    rate.pctUp >= 60 ? 'resolved up more often than not' :
    rate.pctUp >= 53 ? 'barely better than a coin flip' :
    rate.pctUp >= 47 ? 'a coin flip' :
    'resolved down more often than not';
  const versus = rate.pctBeatBench >= 55 ? 'and it beat the index' : rate.pctBeatBench >= 45 ? 'and it roughly matched the index' : 'and it lagged the index';
  return `Historically ${edge}, ${versus}.`;
}

/** The regime split, when there is enough of both to compare. This is usually the most
 *  interesting line in a calibration and it was never shown. */
export function regimeRead(rate: ScreenCalibration): string | null {
  if (rate.bullN < 30 || rate.bearN < 30) return null;
  const gap = rate.bearPctUp - rate.bullPctUp;
  if (Math.abs(gap) < 5) return `Holds up about the same in bull and bear tape (${rate.bullPctUp.toFixed(0)}% / ${rate.bearPctUp.toFixed(0)}%).`;
  const stronger = gap > 0 ? 'bear' : 'bull';
  return `Works better in ${stronger} tape — ${rate.bearPctUp.toFixed(0)}% up in bear (n=${rate.bearN}) vs ${rate.bullPctUp.toFixed(0)}% in bull (n=${rate.bullN}).`;
}

export function sampleWindow(rate: ScreenCalibration): string {
  const year = (iso: string) => (iso ? iso.slice(0, 4) : '');
  const start = year(rate.sampleStart);
  const end = year(rate.sampleEnd);
  if (!start || !end) return `n=${rate.n}`;
  return start === end ? `n=${rate.n} · ${start}` : `n=${rate.n} · ${start}–${end}`;
}
