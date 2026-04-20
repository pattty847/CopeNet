import assert from 'node:assert/strict';
import test from 'node:test';

import {
  getConversationDebugHelperText,
  getDebugActionLabel,
  getWorkingSetSectionLabel,
  shouldUseWorkingSetCompactGrid,
} from '../src/lib/agentMobile';

test('conversation debug helper text is hidden on mobile', () => {
  assert.equal(getConversationDebugHelperText(true, false), undefined);
  assert.equal(getConversationDebugHelperText(false, false), 'Conversation debugging');
  assert.equal(getConversationDebugHelperText(false, true), 'Read-only debugging');
});

test('working set section labels compact on mobile', () => {
  assert.equal(getWorkingSetSectionLabel('entities', true), 'Active');
  assert.equal(getWorkingSetSectionLabel('constraints', true), 'Limits');
  assert.equal(getWorkingSetSectionLabel('questions', true), 'Questions');
  assert.equal(getWorkingSetSectionLabel('entities', false), 'Active Entities');
});

test('mobile action labels shorten to fit one row', () => {
  assert.equal(getDebugActionLabel('copy', true), 'Copy');
  assert.equal(getDebugActionLabel('export', true), 'Export');
  assert.equal(getDebugActionLabel('archive', true), 'Archive');
  assert.equal(getDebugActionLabel('copy', false), 'Debug Copy');
});

test('working set uses compact three-up grid on mobile', () => {
  assert.equal(shouldUseWorkingSetCompactGrid(true), true);
  assert.equal(shouldUseWorkingSetCompactGrid(false), false);
});
