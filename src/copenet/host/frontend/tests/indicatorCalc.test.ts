// Per-family numeric fixtures.
//
// The registry-wide sweep in indicatorMath.test.ts proves every indicator is causal,
// finite and deterministic. It cannot prove any of them is CORRECT — a formula with a
// transposed sign satisfies all three. These are the value checks.

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  bollingerBands,
  donchianChannels,
  keltnerChannels,
  supertrend,
} from '../src/sections/market/indicators/calc/bands';
import { hullMovingAverage, rollingVwap, simpleMovingAverage } from '../src/sections/market/indicators/calc/movingAverages';
import {
  averageDirectionalIndex,
  commodityChannelIndex,
  macd,
  moneyFlowIndex,
  rateOfChange,
  relativeStrengthIndex,
  stochastic,
  stochasticRsi,
  williamsR,
} from '../src/sections/market/indicators/calc/momentum';
import {
  averageRangePercent,
  averageTrueRange,
  historicalVolatility,
} from '../src/sections/market/indicators/calc/volatility';
import { chaikinMoneyFlow, onBalanceVolume } from '../src/sections/market/indicators/calc/volume';
import {
  barsFromCloses,
  barsFromOhlcv,
  constantBars,
  edgeRampBars,
  rampBars,
  walkBars,
  zeroVolume,
} from './indicatorFixtures';

const CONTEXT = { barsPerYear: 252 };
const close = (value: number | null) => value as number;

function near(actual: number | null, expected: number, tolerance = 1e-9, label = '') {
  assert.ok(actual != null, `${label} was null`);
  assert.ok(
    Math.abs((actual as number) - expected) <= tolerance,
    `${label} expected ~${expected}, got ${actual}`,
  );
}

// ------------------------------------------------------------------ overlays

test('Bollinger Bands collapse onto the basis when price does not move', () => {
  const bars = constantBars(40, 50);
  const result = bollingerBands(bars, 20, 2, 'close');
  assert.equal(result.upper[30], 50);
  assert.equal(result.middle[30], 50);
  assert.equal(result.lower[30], 50);
});

test('Bollinger Bands sit exactly k population deviations from the basis', () => {
  const bars = barsFromCloses([2, 4, 4, 4, 5, 5, 7, 9]); // mean 5, population sigma 2
  const result = bollingerBands(bars, 8, 2, 'close');
  near(result.middle[7], 5, 1e-12, 'basis');
  near(result.upper[7], 9, 1e-12, 'upper');
  near(result.lower[7], 1, 1e-12, 'lower');
});

test('Keltner width is a multiple of ATR, not of standard deviation', () => {
  const bars = walkBars(120, 3);
  const channel = keltnerChannels(bars, 20, 10, 2, 'close');
  const range = averageTrueRange(bars, 10);
  const i = 100;
  near(close(channel.upper[i]) - close(channel.middle[i]), 2 * close(range[i]), 1e-9, 'upper offset');
  near(close(channel.middle[i]) - close(channel.lower[i]), 2 * close(range[i]), 1e-9, 'lower offset');
});

test('Donchian tracks the window extremes with the current bar included', () => {
  const bars = barsFromOhlcv([
    [1, 10, 1, 5, 1],
    [5, 20, 4, 15, 1],
    [15, 12, 3, 8, 1],
  ]);
  const channel = donchianChannels(bars, 2);
  assert.equal(channel.upper[1], 20);
  assert.equal(channel.lower[1], 1);
  assert.equal(channel.upper[2], 20);
  assert.equal(channel.lower[2], 3);
});

test('rolling VWAP weights by volume, not by bar count', () => {
  const bars = barsFromOhlcv([
    [10, 10, 10, 10, 100],
    [20, 20, 20, 20, 300],
  ]);
  // (10*100 + 20*300) / 400 = 17.5 — the unweighted mean would be 15.
  near(rollingVwap(bars, 2)[1], 17.5, 1e-12, 'vwap');
});

test('rolling VWAP reports nothing rather than an unweighted average when volume is absent', () => {
  const bars = zeroVolume(walkBars(60, 5));
  assert.ok(rollingVwap(bars, 20).every((value) => value === null));
});

test('Hull moving average lags a ramp far less than a simple average of the same length', () => {
  const bars = rampBars(80, 100, 1);
  const hull = hullMovingAverage(bars, 21, 'close');
  const simple = simpleMovingAverage(bars, 21, 'close');
  const price = bars[70].c;
  const hullLag = price - close(hull[70]);
  const smaLag = price - close(simple[70]);
  near(smaLag, 10, 1e-9, 'SMA lag on a unit ramp'); // (21-1)/2
  assert.ok(Math.abs(hullLag) < 1.5, `Hull lag should be near zero, was ${hullLag}`);
});

test('Supertrend flips side when price closes through the trailing stop', () => {
  // Twenty bars up, then twenty hard down: the stop must switch from below to above.
  const closes = [
    ...Array.from({ length: 25 }, (_, i) => 100 + i * 2),
    ...Array.from({ length: 25 }, (_, i) => 148 - i * 4),
  ];
  const bars = barsFromCloses(closes);
  const result = supertrend(bars, 10, 3);
  assert.equal(result.direction[24], 1, 'should be trailing below price at the top of the rally');
  assert.equal(result.direction[49], -1, 'should be trailing above price after the reversal');
  assert.ok(close(result.line[24]) < bars[24].c, 'an uptrend stop sits below price');
  assert.ok(close(result.line[49]) > bars[49].c, 'a downtrend stop sits above price');
});

// ---------------------------------------------------------------- oscillators

test('RSI reproduces a hand-derived Wilder calculation, seed and smoothing both', () => {
  // The standard 20-close teaching series for a 14-period RSI. Expected values are derived
  // here rather than copied from a website: over changes 1..14 the gains total 3.34 and the
  // losses 1.40, so the seed is avgGain 3.34/14 = 0.238571 against avgLoss 1.40/14 = 0.1,
  // giving RS 2.385714 and RSI 100 - 100/3.385714 = 70.4641. Bars 15 and 16 then follow
  // from Wilder's (prev*13 + current)/14 recursion.
  //
  // Widely republished tables quote 70.53 for "this" series; that figure belongs to a
  // slightly different close list, and reproducing it here would mean fitting the code to a
  // transcription error rather than to the arithmetic.
  const bars = barsFromCloses([
    44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08,
    45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64,
  ]);
  const rsi = relativeStrengthIndex(bars, 14, 'close');
  near(rsi[14], 70.4641, 1e-4, 'seed RSI');
  near(rsi[15], 66.2496, 1e-4, 'first smoothed RSI');
  near(rsi[16], 66.4809, 1e-4, 'second smoothed RSI');
  near(rsi[17], 69.3469, 1e-4, 'third smoothed RSI');
});

test('RSI saturates at the extremes and reports the midpoint for a flat series', () => {
  assert.equal(relativeStrengthIndex(rampBars(40, 100, 1), 14, 'close')[30], 100);
  assert.equal(relativeStrengthIndex(rampBars(40, 100, -1), 14, 'close')[30], 0);
  // A dead-flat series has no gains AND no losses. 100 - 100/(1+0/0) is undefined; the
  // honest reading is neutral, not maximally overbought.
  assert.equal(relativeStrengthIndex(constantBars(40), 14, 'close')[30], 50);
});

test('Stochastic pins to the top of its range on a monotonic advance', () => {
  const result = stochastic(edgeRampBars(40, 100, 1), 14, 3, 3);
  near(result.k[30], 100, 1e-9, '%K');
  near(result.d[30], 100, 1e-9, '%D');
});

test('Stochastic reports nothing rather than an extreme when the window has no range', () => {
  const result = stochastic(constantBars(40), 14, 3, 3);
  assert.equal(result.k[30], null);
});

test('Stochastic RSI stays inside 0-100 and is more saturated than its own RSI', () => {
  const bars = walkBars(300, 11);
  const result = stochasticRsi(bars, 14, 14, 3, 3, 'close');
  const rsi = relativeStrengthIndex(bars, 14, 'close');
  const values = result.k.filter((value): value is number => value != null);
  assert.ok(values.length > 100);
  assert.ok(values.every((value) => value >= 0 && value <= 100));
  // StochRSI rescales RSI against its own recent range, so it reaches the conventional
  // 80/20 bands constantly where the underlying RSI rarely leaves the middle.
  const outsideBands = (series: (number | null)[]) =>
    series.filter((value): value is number => value != null && (value > 80 || value < 20)).length;
  assert.ok(
    outsideBands(result.k) > 4 * outsideBands(rsi),
    `StochRSI left the bands ${outsideBands(result.k)} times against RSI's ${outsideBands(rsi)}`,
  );
});

test('MACD is zero everywhere when the two averages cannot diverge', () => {
  const result = macd(constantBars(120, 80), 12, 26, 9, 'close');
  near(result.macd[100], 0, 1e-9, 'macd');
  near(result.signal[100], 0, 1e-9, 'signal');
  near(result.histogram[100], 0, 1e-9, 'histogram');
});

test('MACD is positive on a sustained advance and its histogram is the line less the signal', () => {
  const bars = rampBars(150, 100, 1);
  const result = macd(bars, 12, 26, 9, 'close');
  assert.ok(close(result.macd[120]) > 0);
  near(close(result.histogram[120]), close(result.macd[120]) - close(result.signal[120]), 1e-9, 'histogram');
});

test('Rate of change reports percent or price difference as configured', () => {
  const bars = barsFromCloses([100, 100, 110]);
  near(rateOfChange(bars, 2, 'percent', 'close')[2], 10, 1e-12, 'percent');
  near(rateOfChange(bars, 2, 'difference', 'close')[2], 10, 1e-12, 'difference');
});

test('Rate of change reports nothing rather than infinity across a zero price', () => {
  const bars = barsFromCloses([0, 5, 10]);
  assert.equal(rateOfChange(bars, 2, 'percent', 'close')[2], null);
});

test('CCI is undefined, not zero, when the window has no mean deviation', () => {
  assert.equal(commodityChannelIndex(constantBars(40), 20)[30], null);
});

test('CCI uses mean absolute deviation — a steady advance sits near +100, not far beyond', () => {
  const cci = commodityChannelIndex(rampBars(80, 100, 1), 20);
  // For a linear ramp the mean absolute deviation is exactly (n/4) of a step at n even,
  // which places CCI at a fixed level well inside the +/-200 an stdev-based version reaches.
  assert.ok(close(cci[60]) > 100 && close(cci[60]) < 180, `CCI on a ramp was ${cci[60]}`);
});

test('Williams %R is zero at the top of its range and -100 at the bottom', () => {
  near(williamsR(edgeRampBars(40, 100, 1), 14)[30], 0, 1e-9, 'top of range');
  near(williamsR(edgeRampBars(40, 100, -1), 14)[30], -100, 1e-9, 'bottom of range');
});

test('ADX is undefined on a flat series and high on a clean trend', () => {
  assert.equal(averageDirectionalIndex(constantBars(80), 14, 14).adx[60], null);
  const trending = averageDirectionalIndex(rampBars(120, 100, 2), 14, 14);
  assert.ok(close(trending.adx[100]) > 60, `ADX on a clean ramp was ${trending.adx[100]}`);
  assert.ok(close(trending.plusDi[100]) > close(trending.minusDi[100]));
});

test('MFI reports nothing at all when the instrument carries no volume', () => {
  assert.ok(moneyFlowIndex(zeroVolume(walkBars(80, 9)), 14).every((value) => value === null));
});

test('MFI saturates on an advance carried entirely by up-volume', () => {
  near(moneyFlowIndex(rampBars(60, 100, 1), 14)[40], 100, 1e-9, 'MFI');
});

// ---------------------------------------------------------- volatility, volume

test('ATR on a constant-range series equals that range', () => {
  const bars = barsFromOhlcv(Array.from({ length: 40 }, () => [10, 12, 10, 11, 1] as [number, number, number, number, number]));
  near(averageTrueRange(bars, 14)[30], 2, 1e-9, 'ATR');
});

test('Average range percent measures the high/low excursion', () => {
  const bars = barsFromOhlcv(Array.from({ length: 40 }, () => [100, 102, 100, 101, 1] as [number, number, number, number, number]));
  near(averageRangePercent(bars, 20)[30], 2, 1e-9, 'ADR%');
});

test('Historical volatility is zero when returns never vary', () => {
  near(historicalVolatility(constantBars(60), 20, 'auto', CONTEXT)[40], 0, 1e-12, 'HV');
});

test('Historical volatility annualises by the chart interval unless pinned', () => {
  const bars = walkBars(200, 13);
  const auto = historicalVolatility(bars, 20, 'auto', { barsPerYear: 52 });
  const weekly = historicalVolatility(bars, 20, '52', CONTEXT);
  const daily = historicalVolatility(bars, 20, '252', CONTEXT);
  near(close(auto[100]), close(weekly[100]), 1e-9, 'auto follows the supplied interval');
  // sqrt(252/52) = 2.2 — hardcoding 252 on a weekly chart overstates by exactly this.
  near(close(daily[100]) / close(weekly[100]), Math.sqrt(252 / 52), 1e-9, 'annualisation ratio');
});

test('OBV adds volume on up closes and subtracts it on down closes', () => {
  const bars = barsFromOhlcv([
    [10, 10, 10, 10, 100],
    [10, 11, 10, 11, 200],
    [11, 11, 10, 10, 300],
    [10, 12, 10, 12, 400],
  ]);
  assert.deepEqual(onBalanceVolume(bars), [0, 200, -100, 300]);
});

test('OBV is unavailable rather than flat when volume is absent', () => {
  assert.ok(onBalanceVolume(zeroVolume(walkBars(40, 17))).every((value) => value === null));
});

test('Chaikin money flow reaches +1 closing at the high and -1 closing at the low', () => {
  const atHigh = barsFromOhlcv(Array.from({ length: 30 }, () => [10, 12, 8, 12, 500] as [number, number, number, number, number]));
  const atLow = barsFromOhlcv(Array.from({ length: 30 }, () => [10, 12, 8, 8, 500] as [number, number, number, number, number]));
  near(chaikinMoneyFlow(atHigh, 20)[25], 1, 1e-12, 'closing at the high');
  near(chaikinMoneyFlow(atLow, 20)[25], -1, 1e-12, 'closing at the low');
});

test('Chaikin money flow counts a zero-range bar as neutral, not as a skipped bar', () => {
  // Half the bars close at their high, half have no range at all. The doji contributes zero
  // money flow but its volume still sits in the denominator, so the result is 0.5, not 1.
  const bars = barsFromOhlcv(
    Array.from({ length: 20 }, (_, i) =>
      (i % 2 === 0 ? [10, 12, 8, 12, 100] : [10, 10, 10, 10, 100]) as [number, number, number, number, number]),
  );
  near(chaikinMoneyFlow(bars, 20)[19], 0.5, 1e-12, 'CMF');
});
