import assert from 'node:assert/strict';
import test from 'node:test';

import { latestActivityTitle, segmentTrail, splitTurn, summarizeToolParts, toolRowTitle } from '../src/runtime/turnTrail';
import type { MessagePart } from '../src/types/backend';

function toolResult(toolId: string, target: string | null = null, ok = true, activityTitle?: string): MessagePart {
  return { kind: 'tool_result', toolId, ok, summary: '', callId: null, target, activityTitle } as unknown as MessagePart;
}

const text = (content: string): MessagePart => ({ kind: 'text', content });

test('the header reads like the work: counts for many, the file name for one', () => {
  const summary = summarizeToolParts([
    toolResult('shell.exec', 'ls tests'),
    toolResult('shell.exec', 'git status'),
    toolResult('files.read', 'src/copenet/core/market/model_tables.py'),
  ]);
  assert.equal(summary, 'Ran 2 commands, read model_tables.py');
});

test('one command still reads naturally', () => {
  assert.equal(summarizeToolParts([toolResult('shell.exec', 'pwd')]), 'Ran a command');
});

test('a model title names its own row; a header covering several calls stays derived', () => {
  const parts = [
    toolResult('files.rg', 'session lock', true, 'Tracing session lock enforcement'),
    toolResult('files.read', 'src/copenet/core/sessions/store.py', true, 'Reading the session store'),
  ];
  assert.equal(summarizeToolParts(parts), 'Ran a search, read store.py');
  assert.equal(latestActivityTitle(parts), 'Reading the session store');
  assert.deepEqual(
    toolRowTitle('files.rg', 'session lock', { activityTitle: 'Tracing session lock enforcement' }),
    { label: 'Tracing session lock enforcement', detail: null, literal: false },
  );
});

test('a group with no model titles has no live title to show', () => {
  assert.equal(latestActivityTitle([toolResult('shell.exec', 'pwd')]), null);
});

test('a chat-only turn says so rather than rendering an empty header', () => {
  assert.equal(summarizeToolParts([]), 'No tools used');
  assert.equal(summarizeToolParts([text('hello')]), 'No tools used');
});

test('failures do not change the header — the failed badge carries that', () => {
  assert.equal(summarizeToolParts([toolResult('files.rg', 'a', false), toolResult('files.rg', 'b')]), 'Ran 2 searches');
});

test('narration closes a tool group, so a later call never jumps above earlier text', () => {
  const segments = segmentTrail([
    toolResult('files.read', 'a.py'),
    toolResult('files.read', 'b.py'),
    text('Only line 107.'),
    toolResult('shell.exec', 'ls'),
  ]);
  assert.deepEqual(segments.map((segment) => segment.kind), ['tools', 'text', 'tools']);
  assert.equal(segments[0].kind === 'tools' && segments[0].parts.length, 2);
});

test('the answer is the text after the last action; earlier narration stays in the trail', () => {
  const parts = [text('Let me look.'), toolResult('files.read', 'a.py'), text('Found it.')];
  const { trail, answer } = splitTurn(parts);
  assert.equal(trail.length, 2);
  assert.deepEqual(answer, [text('Found it.')]);
});

test('a turn with no actions is all answer', () => {
  const { trail, answer } = splitTurn([text('Hello.')]);
  assert.equal(trail.length, 0);
  assert.equal(answer.length, 1);
});

test('a shell row shows the command as typed; a file row shows a short path', () => {
  assert.deepEqual(toolRowTitle('shell.exec', 'ls tests/unit | grep chart'), {
    label: 'Ran shell command:',
    detail: 'ls tests/unit | grep chart',
    literal: true,
  });
  assert.deepEqual(toolRowTitle('files.read', 'src/copenet/core/market/model_tables.py', { inFlight: true }), {
    label: 'Reading',
    detail: '…/market/model_tables.py',
    literal: false,
  });
});

test('a tool with no phrase yet falls back to its own summary, not its raw id', () => {
  assert.equal(toolRowTitle('market.quote', null, { summary: 'Quoted AAPL' }).label, 'Quoted AAPL');
});
