import assert from 'node:assert/strict';
import test from 'node:test';

import {
  CHART_RANGES,
  INTRADAY_RANGES,
  INTRADAY_TIMEFRAMES,
  isIntradayTimeframe,
  rangeForTimeframe,
  rangesFor,
  timeframeLabel,
  visibleBars,
} from '../src/sections/market/chartRanges';
import { barsPerYear } from '../src/sections/market/indicators/compute';

test('the intraday list mirrors what the backend can serve', () => {
  // These divide a native grain the fetch lane requests; the backend refuses anything else,
  // so a mismatch here would be an interval the selector offers and the server rejects.
  assert.deepEqual([...INTRADAY_TIMEFRAMES], ['1m', '2m', '3m', '5m', '10m', '15m', '20m', '30m', '1h', '2h', '4h']);
});

test('a timeframe knows which lane it reads from', () => {
  assert.equal(isIntradayTimeframe('5m'), true);
  assert.equal(isIntradayTimeframe('4h'), true);
  assert.equal(isIntradayTimeframe('D'), false);
  assert.equal(isIntradayTimeframe('W'), false);
});

test('ranges follow the lane', () => {
  assert.deepEqual([...rangesFor('5m')], INTRADAY_RANGES);
  assert.deepEqual([...rangesFor('D')], CHART_RANGES);
});

test('switching lanes keeps a range that still applies and falls back when it does not', () => {
  // 5Y on a 5m chart would filter every bar away — the vendor only serves 60 days.
  assert.equal(rangeForTimeframe('5Y', '5m'), 'MAX');
  assert.equal(rangeForTimeframe('1D', 'D'), 'MAX');
  // MAX is valid in both lanes and survives the switch.
  assert.equal(rangeForTimeframe('MAX', '5m'), 'MAX');
  assert.equal(rangeForTimeframe('5D', '5m'), '5D');
  assert.equal(rangeForTimeframe('1Y', 'D'), '1Y');
});

test('an intraday range actually cuts intraday bars', () => {
  const day = 86400;
  const now = 1_788_000_000;
  const bars = [
    { t: now - 20 * day },
    { t: now - 3 * day },
    { t: now - 3600 },
    { t: now },
  ];

  assert.equal(visibleBars(bars, '1D').length, 2);
  assert.equal(visibleBars(bars, '5D').length, 3);
  assert.equal(visibleBars(bars, 'MAX').length, 4);
});

test('annualisation counts the regular session, not the daily 252', () => {
  // Getting this wrong is quiet: annualisation scales by the square root, so serving a 5m
  // chart the daily 252 would understate historical volatility by about 8.8x.
  assert.equal(barsPerYear('D'), 252);
  assert.equal(barsPerYear('W'), 52);
  assert.equal(barsPerYear('M'), 12);
  assert.equal(barsPerYear('5m'), 78 * 252);
  assert.equal(barsPerYear('1m'), 390 * 252);
  assert.equal(barsPerYear('1h'), Math.round((390 / 60) * 252));
});

test('every offered interval annualises to something finite and larger than daily', () => {
  for (const timeframe of INTRADAY_TIMEFRAMES) {
    const bars = barsPerYear(timeframe);
    assert.ok(Number.isFinite(bars) && bars > 252, `${timeframe} annualised to ${bars}`);
  }
});

test('intraday intervals get a readable label', () => {
  assert.equal(timeframeLabel('5m'), '5 minute');
  assert.equal(timeframeLabel('1h'), '1 hour');
  assert.equal(timeframeLabel('D'), 'Daily');
});
