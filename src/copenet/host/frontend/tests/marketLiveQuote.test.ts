import assert from 'node:assert/strict';
import test from 'node:test';
import { createMarketQuoteApi, type QuoteEvent } from '../src/lib/wsMarketQuote';

test('ticker stream ignores late events and old cleanup does not clear a new viewer', async () => {
  const calls: { method: string; params: Record<string, unknown> }[] = [];
  const api = createMarketQuoteApi(
    async <T extends Record<string, unknown>>(method: string, params: Record<string, unknown>) => {
      calls.push({ method, params });
      return {} as T;
    },
    () => true,
  );
  const events: QuoteEvent[] = [];
  const first = api.open('TEST', (event) => events.push(event));
  const firstId = calls[0].params.subscriptionId;
  const second = api.open('DEMO', (event) => events.push(event));
  const secondId = calls[1].params.subscriptionId;
  first.close();
  api.receive({ subscriptionId: firstId, symbol: 'TEST', status: 'streaming', quote: null });
  api.receive({ subscriptionId: secondId, symbol: 'TEST', status: 'streaming', quote: null });
  assert.equal(events.length, 0);
  api.receive({ subscriptionId: secondId, symbol: 'DEMO', status: 'waiting', quote: null });
  assert.equal(events.length, 1);
  first.renew();
  assert.equal(calls.length, 3);
  second.renew();
  assert.equal(calls[3].params.subscriptionId, secondId);
  second.close();
  api.receive({ subscriptionId: secondId, symbol: 'DEMO', status: 'streaming', quote: null });
  assert.equal(events.length, 1);
});

test('departing or renewing an offline ticker never reconnects the host', () => {
  let connected = true;
  let calls = 0;
  const api = createMarketQuoteApi(
    async <T extends Record<string, unknown>>() => {
      calls++;
      return {} as T;
    },
    () => connected,
  );
  const subscription = api.open('TEST', () => undefined);
  assert.equal(calls, 1);
  connected = false;
  subscription.renew();
  subscription.close();
  assert.equal(calls, 1);
});
