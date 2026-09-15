import test from 'node:test';
import assert from 'node:assert/strict';
import { fillMarkers, money, scenario } from '../src/sections/market/position/model';
import type { HeldPosition, PositionFill } from '../src/sections/market/position/types';
const position = { quantity: 20, avg_cost: 100 } as HeldPosition;
const time = (day: string) => Date.parse(`${day}T00:00:00Z`) / 1000;
const bar = (day: string) => ({ t: time(day), o: 100, h: 110, l: 90, c: 105, v: 1000 });
const fill = (day: string, side = 'BUY'): PositionFill => ({ id: day, side, quantity: 10, price: 100, filledAt: `${day}T15:00:00Z`, sessionDate: day, priceSource: 'fill' });
test('position scenarios use signed holdings and never invent missing cost', () => {
  assert.deepEqual(scenario(position, 110), { dollars: 200, percent: 10 });
  assert.deepEqual(scenario({ ...position, quantity: -20 }, 110), { dollars: -200, percent: -10 });
  assert.equal(scenario({ ...position, avg_cost: null }, 110), null);
  assert.equal(scenario(position, NaN), null);
});
test('weekly fills attach to candle week without adding time slots', () => {
  const bars = [bar('2026-01-05'), bar('2026-01-12')];
  const markers = fillMarkers([fill('2026-01-06'), fill('2026-01-08'), fill('2026-01-09', 'SELL'), fill('2026-01-20')], bars, 'W');
  assert.equal(markers.length, 2);
  assert.equal(markers[0].time, bars[0].t);
  assert.equal(markers[0].text, 'Buy ×2');
  assert.equal(markers[1].text, 'Sell');
});
test('daily fills outside the visible candles never snap to an unrelated session', () => {
  assert.deepEqual(fillMarkers([fill('2026-01-02'), fill('2026-01-06')], [bar('2026-01-05')], 'D'), []);
});

test('intraday fill markers never span overnight or missing candle gaps', () => {
  const stamp = (value: string) => Date.parse(value) / 1000;
  const bars = ['2026-01-05T20:55:00Z', '2026-01-06T14:30:00Z'].map((value) => ({ ...bar('2026-01-05'), t: stamp(value) }));
  const at = (value: string) => ({ ...fill('2026-01-05'), filledAt: value });
  const missing = ['2026-01-05T21:01:00Z', '2026-01-06T14:40:00Z'];
  assert.deepEqual(fillMarkers(missing.map(at), bars, '5m'), []);
  assert.equal(fillMarkers([at('2026-01-06T14:34:59Z')], bars, '5m')[0].time, bars[1].t);
});
test('short orders have explicit markers and unknown currency stays unknown', () => {
  assert.equal(fillMarkers([fill('2026-01-05', 'SHORT')], [bar('2026-01-05')])[0].text, 'Short');
  assert.match(money(100, null), /currency unknown/);
  assert.equal(money(null, null), '—');
});
