import assert from 'node:assert/strict';
import test from 'node:test';

import { summarizeToolParts } from '../src/components/transcript/TurnToolGroup';
import type { MessagePart } from '../src/types/backend';

function toolResult(toolId: string, ok = true): MessagePart {
  return { kind: 'tool_result', toolId, ok, summary: '', callId: null } as MessagePart;
}

test('the header counts by operator verb, not by tool id', () => {
  const summary = summarizeToolParts([
    toolResult('files.rg'),
    toolResult('files.read'),
    toolResult('files.read'),
    toolResult('shell.exec'),
  ]);

  assert.equal(summary, 'Searched 1×, read 2×, ran command 1×');
});

test('one call still reads naturally', () => {
  assert.equal(summarizeToolParts([toolResult('shell.exec')]), 'Ran command 1×');
});

test('a chat-only turn says so rather than rendering an empty header', () => {
  assert.equal(summarizeToolParts([]), 'No tools used');
  assert.equal(
    summarizeToolParts([{ kind: 'text', content: 'hello' } as MessagePart]),
    'No tools used',
  );
});

test('failures do not change the header — the failed badge carries that', () => {
  const summary = summarizeToolParts([toolResult('files.rg', false), toolResult('files.rg')]);
  assert.equal(summary, 'Searched 2×');
});
