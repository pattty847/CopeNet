import assert from 'node:assert/strict';
import test from 'node:test';
import { unseenAlertCount } from '../src/components/chrome/alertInbox';
import type { AlertEvent } from '../src/sections/market/monitoring/types';

function event(evaluatedAt: string): AlertEvent {
  return { eventId: evaluatedAt, alertId: 'a', symbol: 'SPY', timeframe: 'D', condition: 'crosses_above', leftValue: 1, rightValue: 0, candleCloseAt: evaluatedAt, evaluatedAt, scanId: 'morning' };
}

test('the alert badge counts every event when the inbox was never opened', () => {
  assert.equal(unseenAlertCount([event('2026-09-01T14:00:00Z'), event('2026-09-02T14:00:00Z')], ''), 2);
});

test('the alert badge counts only events evaluated after the inbox was last opened', () => {
  const events = [event('2026-09-03T14:00:00Z'), event('2026-09-02T14:00:00Z'), event('2026-09-01T14:00:00Z')];
  assert.equal(unseenAlertCount(events, '2026-09-02T15:00:00Z'), 1);
});
