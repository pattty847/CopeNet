// Series colours for indicators.
//
// Orange is not in this palette, and that is the point. The workspace grammar gives
// `--mkt-accent` exactly one meaning — an armed tool — so an indicator that borrowed it would
// read as "this control is active" from across the room. Indicators draw from their own hue
// set; green and red appear only where they carry their existing meaning (direction), never
// as a way to tell two moving averages apart.

export const SERIES_COLORS = {
  blue: '#8fb8e8',
  gold: '#d9ad67',
  violet: '#c594e8',
  rose: '#e37d9f',
  teal: '#6fc3c0',
  sand: '#b7ad9c',
  slate: '#7f93ad',
  up: '#69c589',
  down: '#d96d5f',
  neutral: '#a29b90',
} as const;

/** Band edges are the same series drawn twice, so they share a colour and the midline is
 *  dimmed — three equally-weighted lines read as three indicators rather than one channel. */
export const BAND_EDGE = SERIES_COLORS.slate;
export const BAND_MID = SERIES_COLORS.sand;

/** Reference lines are furniture: visible enough to read a level against, quiet enough that
 *  they never compete with the series they frame. */
export const REFERENCE_LINE = 'rgba(254,252,244,.20)';
export const REFERENCE_ZERO = 'rgba(254,252,244,.32)';

/** Cycle through the palette so two instances of the same indicator are never the same
 *  colour by default. Deterministic in the instance's ordinal, not random. */
const ROTATION = [
  SERIES_COLORS.blue,
  SERIES_COLORS.gold,
  SERIES_COLORS.violet,
  SERIES_COLORS.teal,
  SERIES_COLORS.rose,
  SERIES_COLORS.slate,
];

export function rotatedColor(ordinal: number): string {
  return ROTATION[((ordinal % ROTATION.length) + ROTATION.length) % ROTATION.length];
}

/** Magnitude-aware default for a legend value. Overridden per definition via `format`. */
export function formatIndicatorValue(value: number): string {
  const magnitude = Math.abs(value);
  if (magnitude >= 1e12) return `${(value / 1e12).toFixed(2)}T`;
  if (magnitude >= 1e9) return `${(value / 1e9).toFixed(2)}B`;
  if (magnitude >= 1e6) return `${(value / 1e6).toFixed(2)}M`;
  if (magnitude >= 1000) return value.toFixed(0);
  if (magnitude >= 1) return value.toFixed(2);
  if (magnitude === 0) return '0';
  return value.toFixed(4);
}
