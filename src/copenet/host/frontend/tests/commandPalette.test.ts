import assert from 'node:assert/strict';
import test from 'node:test';

import {
  shouldAutoScrollCommandPalette,
} from '../src/lib/commandPalette';

test('command palette does not auto-scroll on open before interaction', () => {
  assert.equal(
    shouldAutoScrollCommandPalette({ query: '', interaction: 'idle' }),
    false,
  );
});

test('command palette auto-scrolls after query or result navigation', () => {
  assert.equal(
    shouldAutoScrollCommandPalette({ query: 'session', interaction: 'query' }),
    true,
  );
  assert.equal(
    shouldAutoScrollCommandPalette({ query: '', interaction: 'keyboard' }),
    true,
  );
  assert.equal(
    shouldAutoScrollCommandPalette({ query: '', interaction: 'mouse' }),
    true,
  );
});
