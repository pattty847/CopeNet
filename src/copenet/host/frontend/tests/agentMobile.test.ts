import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getConversationActionTriggerLabel,
  getDebugActionLabel,
} from '../src/lib/agentMobile';

test('mobile action labels shorten to fit one row', () => {
  assert.equal(getDebugActionLabel('copy', true), 'Copy');
  assert.equal(getDebugActionLabel('export', true), 'Export');
  assert.equal(getDebugActionLabel('archive', true), 'Archive');
  assert.equal(getDebugActionLabel('copy', false), 'Debug Copy');
  assert.equal(getConversationActionTriggerLabel(true), 'Actions');
  assert.equal(getConversationActionTriggerLabel(false), 'Actions');
});
