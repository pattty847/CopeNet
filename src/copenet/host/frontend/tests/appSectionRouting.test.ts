import assert from 'node:assert/strict';
import test from 'node:test';

import {
  APP_SECTION_PATHS,
  appSectionFromPathname,
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
  assert.equal(appSectionFromPathname('/agents/'), 'agents');
  assert.equal(appSectionFromPathname('/not-a-section'), 'home');
});

test('section navigation pushes only when the top-level path changes', () => {
  const pushed: string[] = [];

  assert.equal(pushAppSectionPath('market', '/', (path) => pushed.push(path)), true);
  assert.equal(pushAppSectionPath('market', '/market/', (path) => pushed.push(path)), false);
  assert.deepEqual(pushed, ['/market']);
});
