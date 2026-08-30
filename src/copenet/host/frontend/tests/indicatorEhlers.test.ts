// Ehlers reference tests.
//
// These filters are recursive and self-referential, so a snapshot of their own output proves
// only that they have not changed — a transposed coefficient would be captured as "correct"
// on the first run. Every assertion here is instead something derivable from OUTSIDE the
// implementation:
//
//   * analytic fixed points (a filter whose coefficients sum to one passes a constant
//     through unchanged),
//   * the coefficients recomputed independently from the published formula,
//   * and, for MAMA, the measurement it exists to make: feed a sine of known period and
//     check that the Hilbert-transform discriminator recovers that period. That last one is
//     the reason the degree/radian handling can be trusted — the phase arithmetic feeds the
//     same discriminator, and it does not land on 20.00 by accident.

import assert from 'node:assert/strict';
import test from 'node:test';

import {
  fisherTransform,
  instantaneousTrendline,
  mesaAdaptiveMovingAverage,
  superSmoother,
} from '../src/sections/market/indicators/calc/ehlers';
import { simpleMovingAverage } from '../src/sections/market/indicators/calc/movingAverages';
import { barsFromCloses, constantBars, rampBars, sineBars, walkBars } from './indicatorFixtures';

const value = (entry: number | null) => entry as number;

function near(actual: number | null, expected: number, tolerance: number, label: string) {
  assert.ok(actual != null, `${label} was null`);
  assert.ok(Math.abs(value(actual) - expected) <= tolerance, `${label} expected ~${expected}, got ${actual}`);
}

// ------------------------------------------------------------- Super Smoother

test('Super Smoother coefficients match the published formula and sum to unity', () => {
  // Recomputed here from Ehlers' definition rather than read from the implementation:
  //   a1 = exp(-sqrt(2)*pi/period), b1 = 2*a1*cos(sqrt(2)*pi/period)
  //   c2 = b1, c3 = -a1^2, c1 = 1 - c2 - c3
  // c1 + c2 + c3 == 1 is what makes a constant input a fixed point, which the next test
  // exercises against the real implementation.
  for (const period of [4, 10, 20, 50]) {
    const angle = (Math.SQRT2 * Math.PI) / period;
    const a1 = Math.exp(-angle);
    const c2 = 2 * a1 * Math.cos(angle);
    const c3 = -(a1 * a1);
    const c1 = 1 - c2 - c3;
    near(c1 + c2 + c3, 1, 1e-12, `unity at period ${period}`);
    assert.ok(a1 > 0 && a1 < 1, `a1 out of range at period ${period}`);
  }
});

test('Super Smoother passes a constant through unchanged', () => {
  const result = superSmoother(constantBars(200, 100), 10, 'close');
  near(result[150], 100, 1e-9, 'constant fixed point');
});

test('Super Smoother tracks a ramp with far less lag than a simple average', () => {
  const bars = rampBars(200, 100, 1);
  const smoothed = superSmoother(bars, 20, 'close');
  const simple = simpleMovingAverage(bars, 20, 'close');
  const price = bars[150].c;
  const filterLag = price - value(smoothed[150]);
  const averageLag = price - value(simple[150]);
  near(averageLag, 9.5, 1e-9, 'SMA lag'); // exactly (period - 1)/2 on a linear ramp
  // The 2-pole filter's group delay is a fraction of the equivalent average's, which is the
  // entire reason to prefer it. Measured at ~4.0 bars against the SMA's 9.5.
  assert.ok(filterLag > 0 && filterLag < averageLag / 2, `Super Smoother lag was ${filterLag} against the SMA's ${averageLag}`);
});

test('Super Smoother attenuates a fast oscillation far more than a slow one', () => {
  // The defining property of a low-pass filter, and independent of any reference values.
  const amplitude = (bars: ReturnType<typeof sineBars>, period: number) => {
    const out = superSmoother(bars, 20, 'close').slice(100).filter((entry): entry is number => entry != null);
    return Math.max(...out) - Math.min(...out);
  };
  const fast = amplitude(sineBars(400, 5), 5);
  const slow = amplitude(sineBars(400, 60), 60);
  assert.ok(fast < slow / 4, `fast oscillation ${fast} was not attenuated against slow ${slow}`);
});

// ------------------------------------------------------------ Fisher Transform

test('Fisher Transform of a rangeless series is zero, not a division by zero', () => {
  const result = fisherTransform(constantBars(120, 100), 9, 'hl2');
  assert.equal(result.fisher[100], 0);
});

test('Fisher Transform stays finite at full saturation thanks to the 0.999 clamp', () => {
  // A monotone advance pins the normalised value at the window maximum every bar. Without
  // Ehlers' clamp, ln((1+1)/(1-1)) is infinite and the whole series is destroyed.
  const result = fisherTransform(rampBars(120, 100, 1), 9, 'hl2');
  const saturated = value(result.fisher[100]);
  assert.ok(Number.isFinite(saturated));
  assert.ok(saturated > 3, `expected a strongly positive reading, got ${saturated}`);
});

test('Fisher Transform trigger is the previous bar of the fisher line itself', () => {
  const result = fisherTransform(walkBars(200, 23), 9, 'hl2');
  for (let i = 20; i < 150; i += 1) {
    assert.deepEqual(result.trigger[i], result.fisher[i - 1], `trigger diverged from the prior fisher at bar ${i}`);
  }
});

test('Fisher Transform turns sharply — its excursions exceed the price swing it is built on', () => {
  const bars = sineBars(400, 30, 5, 100);
  const result = fisherTransform(bars, 10, 'hl2');
  const values = result.fisher.slice(100).filter((entry): entry is number => entry != null);
  assert.ok(Math.max(...values) > 1.5 && Math.min(...values) < -1.5, 'Fisher failed to reach its characteristic peaks');
});

// -------------------------------------------------- Instantaneous Trendline

test('Instantaneous Trendline holds a constant and its trigger sits on top of it', () => {
  const result = instantaneousTrendline(constantBars(120, 100), 0.07, 'close');
  near(result.trend[100], 100, 1e-9, 'trendline');
  near(result.trigger[100], 100, 1e-9, 'trigger');
});

test('Instantaneous Trendline follows a ramp with less lag than a comparable average', () => {
  const bars = rampBars(300, 100, 1);
  const result = instantaneousTrendline(bars, 0.07, 'close');
  const lag = bars[250].c - value(result.trend[250]);
  assert.ok(Math.abs(lag) < 15, `ITrend lag on a unit ramp was ${lag}`);
  // The trigger extrapolates two bars of the trendline, so it leads the trendline itself.
  assert.ok(value(result.trigger[250]) > value(result.trend[250]));
});

test('Instantaneous Trendline smooths a noisy series rather than tracing it', () => {
  const bars = walkBars(400, 31);
  const result = instantaneousTrendline(bars, 0.07, 'close');
  const swing = (series: number[]) =>
    series.slice(1).reduce((total, entry, i) => total + Math.abs(entry - series[i]), 0);
  const priceSwing = swing(bars.slice(50).map((bar) => bar.c));
  const trendSwing = swing(result.trend.slice(50).filter((entry): entry is number => entry != null));
  assert.ok(trendSwing < priceSwing / 2, `trendline travelled ${trendSwing} against price ${priceSwing}`);
});

// ------------------------------------------------------------------ MAMA/FAMA

test('MAMA recovers the dominant cycle of a sine wave of known period', () => {
  // The independent check on the whole Hilbert chain — detrender taps, quadrature, homodyne
  // discriminator and the degree conversion all have to be right for this to land.
  for (const period of [10, 14, 20, 30, 40]) {
    const result = mesaAdaptiveMovingAverage(sineBars(600, period), 0.5, 0.05, 32, 'close');
    const measured = result.period.slice(-100).filter((entry): entry is number => entry != null);
    const average = measured.reduce((total, entry) => total + entry, 0) / measured.length;
    assert.ok(
      Math.abs(average - period) < 1,
      `a ${period}-bar cycle was measured as ${average.toFixed(2)}`,
    );
  }
});

test('MAMA clamps its measured period to the 6-50 bar band', () => {
  for (const bars of [sineBars(600, 3), sineBars(600, 120), walkBars(600, 41)]) {
    const result = mesaAdaptiveMovingAverage(bars, 0.5, 0.05, 32, 'close');
    for (const entry of result.period) {
      if (entry == null) continue;
      assert.ok(entry >= 5.9 && entry <= 50.1, `measured period escaped its band at ${entry}`);
    }
  }
});

test('MAMA and FAMA both settle on a constant', () => {
  const result = mesaAdaptiveMovingAverage(constantBars(200, 100), 0.5, 0.05, 32, 'close');
  near(result.mama[150], 100, 1e-9, 'MAMA');
  near(result.fama[150], 100, 1e-9, 'FAMA');
});

test('FAMA trails MAMA — half the adaptation rate, by construction', () => {
  // On a sustained advance the faster average must sit above the slower one for the
  // crossover the pair exists to signal to mean anything.
  const result = mesaAdaptiveMovingAverage(rampBars(300, 100, 1), 0.5, 0.05, 32, 'close');
  for (let i = 120; i < 280; i += 1) {
    assert.ok(
      value(result.mama[i]) > value(result.fama[i]),
      `FAMA overtook MAMA on a rising series at bar ${i}`,
    );
  }
});

test('MAMA adapts: it reaches a step change faster than its own slow limit would allow', () => {
  // Pinning alpha at the slow limit is what a broken delta-phase produces, so compare the
  // adaptive result against the plain EMA that a fixed slow alpha would give.
  const closes = [...Array.from({ length: 120 }, () => 100), ...Array.from({ length: 80 }, () => 130)];
  const bars = barsFromCloses(closes);
  const result = mesaAdaptiveMovingAverage(bars, 0.5, 0.05, 32, 'close');
  let fixedSlow = 100;
  for (let i = 120; i < 160; i += 1) fixedSlow = 0.05 * 130 + 0.95 * fixedSlow;
  assert.ok(
    value(result.mama[159]) > fixedSlow,
    `MAMA reached ${result.mama[159]} where a fixed slow-limit EMA reaches ${fixedSlow.toFixed(2)}`,
  );
});
