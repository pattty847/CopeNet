import assert from 'node:assert/strict';
import test from 'node:test';
import { magnetSnap } from '../src/sections/market/drawings/magnet';

const bar = { t: 100, o: 50, h: 60, l: 40, c: 55, v: 1 };
const toY = (price: number) => 400 - price * 4; // high=160, close=180, open=200, low=240

test('weak magnet sticks only when the cursor is already near a candle price', () => {
  assert.deepEqual(magnetSnap(bar, 165, toY, 'weak', 14), { value: 60, y: 160, field: 'h' });
  assert.equal(magnetSnap(bar, 120, toY, 'weak', 14), null, 'far above the high the cursor stays free');
  assert.deepEqual(magnetSnap(bar, 225, toY, 'weak', 28), { value: 40, y: 240, field: 'l' }, 'a fingertip reaches further');
});

test('strong magnet always takes the nearest of open, high, low and close, and says which', () => {
  assert.deepEqual(magnetSnap(bar, 20, toY, 'strong', 14), { value: 60, y: 160, field: 'h' });
  assert.deepEqual(magnetSnap(bar, 188, toY, 'strong', 14), { value: 55, y: 180, field: 'c' });
  assert.equal(magnetSnap(bar, 160, toY, 'off', 14), null);
});
