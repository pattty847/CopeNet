import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';

import { TurnTrail } from '../src/components/transcript/TurnTrail';
import type { MessagePart } from '../src/types/backend';

function toolResult(toolId: string, target: string): MessagePart {
  return { kind: 'tool_result', toolId, ok: true, summary: '', callId: `${toolId}:${target}`, target, at: '' } as MessagePart;
}

const parts: MessagePart[] = [
  { kind: 'text', content: 'Only line 107. Let me check the tests.' },
  toolResult('shell.exec', 'ls tests/unit'),
  toolResult('files.read', 'tests/unit/test_chart_model_tables.py'),
  { kind: 'text', content: 'The existing test claims the JSON path stays exact.' },
  toolResult('shell.exec', 'rg format_resource'),
  { kind: 'text', content: 'Final answer here.' },
];

test('a live turn renders in order: narration, a collapsed group, narration, a bare row', () => {
  const html = renderToStaticMarkup(<TurnTrail parts={parts} isLive sessionKey="s" runId="r" />);
  const order = ['Only line 107', 'Ran a command, read test_chart_model_tables.py', 'The existing test claims', 'rg format_resource', 'Final answer here']
    .map((needle) => html.indexOf(needle));
  assert.ok(order.every((at) => at >= 0), `missing a segment: ${order}`);
  assert.deepEqual([...order].sort((a, b) => a - b), order);
  // Collapsed: the group's rows are not in the DOM until it is opened.
  assert.equal(html.includes('ls tests/unit'), false);
  assert.equal(html.includes('Context it saw'), false);
});

test('a settled turn folds everything before the answer into one collapsed box', () => {
  const html = renderToStaticMarkup(<TurnTrail parts={parts} sessionKey="s" runId="r" />);
  assert.ok(html.includes('Ran 2 commands, read test_chart_model_tables.py'));
  assert.equal(html.includes('Only line 107'), false);
  assert.equal(html.includes('The existing test claims'), false);
  assert.ok(html.indexOf('Ran 2 commands') < html.indexOf('Final answer here'));
  assert.ok(html.indexOf('Final answer here') < html.indexOf('Context it saw'));
});

test('a settled chat-only turn keeps its context row and gets no box', () => {
  const html = renderToStaticMarkup(
    <TurnTrail parts={[{ kind: 'text', content: 'Hello.' }]} sessionKey="s" runId="r" />,
  );
  assert.ok(html.includes('Hello.'));
  assert.ok(html.includes('Context it saw'));
  assert.equal(html.includes('aria-expanded'), false);
});
