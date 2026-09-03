import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';
import { newAlert, newScan, symbolsFromText, toggleValue, timeLabel } from '../src/sections/market/monitoring/model';
import { projectPriceAlerts } from '../src/sections/market/usePriceAlerts';
import { createMarketMonitoringApi } from '../src/lib/wsMarketMonitoring';
import { ScanScope } from '../src/sections/market/monitoring/ScanEditor';

test('new scan is small by default with explicit New York09:45 weekday schedule', () => {
  const scan = newScan();
  assert.equal(scan.includeUniverse, false);
  assert.deepEqual(scan.sources, ['prices']);
  assert.deepEqual(scan.times, ['09:45']);
  assert.equal(scan.timezone, 'America/New_York');
  assert.equal(scan.publishBrief, false);
  assert.deepEqual(symbolsFromText('test, TEST; voo\nqqq'), ['TEST', 'VOO', 'QQQ']);
  assert.deepEqual(toggleValue(['TEST', 'VOO'], 'TEST'), ['VOO']);
});

test('new alert starts with explicit authorization off and no hidden schedule', () => {
  const rule = newAlert('TEST');
  assert.equal(rule.scanId, '');
  assert.equal(rule.timeframe, 'daily');
  assert.equal(rule.telegramAuthorized, false);
  assert.deepEqual(rule.destinationIds, []);
});

test('chart price lines project canonical enabled price rules only', () => {
  const technical = newAlert('TEST');
  const price = { ...technical, alertId: 'price', left: { kind: 'price' as const }, right: { kind: 'constant' as const, value: 100 } };
  assert.deepEqual(projectPriceAlerts([technical, price, { ...price, enabled: false }, { ...price, symbol: 'OTHER' }], 'TEST'), [
    { alertId: 'price', symbol: 'TEST', direction: 'above', threshold: 100 },
  ]);
});

test('read-only monitoring methods never issue run or delivery requests', async () => {
  const calls: string[] = [];
  const api = createMarketMonitoringApi(async (method) => {
    calls.push(method);
    return {} as never;
  });
  await Promise.all([api.scans(), api.alerts(), api.catalogue(), api.notifications()]);
  assert.deepEqual(calls, ['market.scans.get', 'market.alerts.state', 'market.alerts.catalogue', 'market.notifications.get']);
});

test('scope preview labels source jobs rather than promising an HTTP request count', () => {
  const html = renderToStaticMarkup(
    <ScanScope
      preview={{
        scopeToken: 'synthetic',
        resolvedSymbols: ['TEST'],
        contextSymbols: [],
        inclusions: [{ symbol: 'TEST', reasons: ['Direct selection'] }],
        issues: [],
        notes: ['Issuer filings only'],
        cacheHits: 0,
        fetchSymbols: ['TEST'],
        work: [{ symbol: 'TEST', source: 'sec', status: 'fetch' }],
      }}
    />,
  );
  assert.match(html, /source jobs/);
  assert.match(html, /multiple HTTP requests/);
  assert.match(html, /Issuer filings only/);
  assert.equal(timeLabel(null), 'Not scheduled');
});
