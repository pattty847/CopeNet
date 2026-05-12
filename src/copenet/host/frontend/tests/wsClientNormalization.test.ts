import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeAssistantDisplayText } from '../src/lib/wsClient';

test('normalizeAssistantDisplayText leaves ordinary assistant prose alone', () => {
  const normalized = normalizeAssistantDisplayText('Normal assistant response.');

  assert.equal(normalized, 'Normal assistant response.');
});

test('normalizeAssistantDisplayText leaves structured-looking content untouched', () => {
  const raw = '{"type":"legacy_structured_answer","content":"Hello there."}';
  const normalized = normalizeAssistantDisplayText(raw);

  assert.equal(normalized, raw);
});
