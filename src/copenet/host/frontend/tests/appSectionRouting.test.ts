import assert from 'node:assert/strict';
import test from 'node:test';

import {
  APP_SECTION_PATHS,
  appSectionFromPathname,
  marketFormulaFromLocation,
  marketFormulaPath,
  marketResultNavigationPath,
  marketTickerFromPathname,
  marketTickerNavigationPath,
  marketTickerPath,
  pushAppSectionPath,
} from '../src/lib/appSectionRouting';

test('top-level app sections map to stable reloadable paths', () => {
  assert.deepEqual(APP_SECTION_PATHS, {
    home: '/',
    agents: '/agents',
    market: '/market',
    workflows: '/workflows',
    'data-tools': '/data-tools',
    observability: '/observability',
    experiments: '/experiments',
  });

  assert.equal(appSectionFromPathname('/market'), 'market');
  assert.equal(appSectionFromPathname('/market/BRK.A'), 'market');
  assert.equal(appSectionFromPathname('/agents/'), 'agents');
  assert.equal(appSectionFromPathname('/not-a-section'), 'home');
});

test('ticker-to-ticker navigation preserves chart URL state without leaking unrelated queries', () => {
  assert.equal(marketTickerNavigationPath('XLK', '/market/AAPL', '?compare=VOO&view=compare'), '/market/XLK?compare=VOO&view=compare');
  assert.equal(marketTickerNavigationPath('XLK', '/agents', '?session=private'), '/market/XLK');
  assert.equal(marketTickerNavigationPath(null, '/market/AAPL', '?compare=VOO&view=compare'), '/market');
});

test('market ticker paths are reloadable and preserve symbol punctuation', () => {
  assert.equal(marketTickerFromPathname('/market/NVDA'), 'NVDA');
  assert.equal(marketTickerFromPathname('/market/%5EVIX/'), '^VIX');
  assert.equal(marketTickerFromPathname('/market'), null);
  assert.equal(marketTickerFromPathname('/market/NVDA/events'), null);
  assert.equal(marketTickerFromPathname('/market/formula'), null);
  assert.equal(marketTickerPath('brk.a'), '/market/BRK.A');
  assert.equal(marketTickerPath('^vix'), '/market/%5EVIX');
  assert.equal(marketTickerPath(null), '/market');
});

test('formula symbols use a distinct reloadable route', () => {
  assert.equal(marketFormulaPath('VOO / GLD'), '/market/formula?expression=VOO+%2F+GLD');
  assert.equal(marketFormulaFromLocation('/market/formula', '?expression=VOO+%2F+GLD'), 'VOO / GLD');
  assert.equal(marketFormulaFromLocation('/market/AAPL', '?expression=VOO'), null);
  assert.equal(
    marketResultNavigationPath({ type: 'formula', symbol: 'VOO / GLD' }, '/market/AAPL', '?compare=QQQ'),
    '/market/formula?expression=VOO+%2F+GLD',
  );
});

test('section navigation pushes only when the top-level path changes', () => {
  const pushed: string[] = [];

  assert.equal(pushAppSectionPath('market', '/', (path) => pushed.push(path)), true);
  assert.equal(pushAppSectionPath('market', '/market/', (path) => pushed.push(path)), false);
  assert.deepEqual(pushed, ['/market']);
});
