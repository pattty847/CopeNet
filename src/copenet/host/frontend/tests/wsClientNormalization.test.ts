import assert from 'node:assert/strict';
import test from 'node:test';

import { normalizeAssistantDisplayText } from '../src/lib/wsClient';

test('normalizeAssistantDisplayText unwraps FINAL_CANDIDATE content aliases', () => {
  const normalized = normalizeAssistantDisplayText(
    '{"type":"FINAL_CANDIDATE","content":"Hello there.\\n\\nSecond paragraph."}',
  );

  assert.equal(normalized, 'Hello there.\n\nSecond paragraph.');
});

test('normalizeAssistantDisplayText unwraps nested FINAL_CANDIDATE response aliases', () => {
  const normalized = normalizeAssistantDisplayText(
    '{"FINAL_CANDIDATE":{"response":"Nested hello.\\n\\nParagraph two."}}',
  );

  assert.equal(normalized, 'Nested hello.\n\nParagraph two.');
});

test('normalizeAssistantDisplayText leaves ordinary assistant prose alone', () => {
  const normalized = normalizeAssistantDisplayText('Normal assistant response.');

  assert.equal(normalized, 'Normal assistant response.');
});
