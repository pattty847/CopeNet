import assert from 'node:assert/strict';
import test from 'node:test';

import { collapseRenderedMessageParts } from '../src/components/MessageBubble';
import type { MessagePart } from '../src/types/backend';

test('collapseRenderedMessageParts hides tool call rows once the matching result arrives', () => {
  const parts: MessagePart[] = [
    {
      kind: 'tool_call',
      callId: 'call-1',
      toolId: 'files.read',
      hint: 'README.md',
      target: 'README.md',
      at: '2026-05-08T23:55:00.000Z',
    },
    {
      kind: 'tool_result',
      callId: 'call-1',
      toolId: 'files.read',
      ok: true,
      summary: 'Read file README.md.',
      target: 'README.md',
      at: '2026-05-08T23:55:01.000Z',
    },
  ];

  const collapsed = collapseRenderedMessageParts(parts);

  assert.equal(collapsed.length, 1);
  assert.equal(collapsed[0]?.kind, 'tool_result');
});

test('collapseRenderedMessageParts keeps tool call rows when no result has arrived yet', () => {
  const parts: MessagePart[] = [
    {
      kind: 'tool_call',
      callId: 'call-2',
      toolId: 'files.read',
      hint: 'README.md',
      target: 'README.md',
      at: '2026-05-08T23:55:00.000Z',
    },
  ];

  const collapsed = collapseRenderedMessageParts(parts);

  assert.equal(collapsed.length, 1);
  assert.equal(collapsed[0]?.kind, 'tool_call');
});

test('collapseRenderedMessageParts preserves thinking parts inline (Phase 4)', () => {
  const parts: MessagePart[] = [
    { kind: 'thinking', text: 'planning the read' },
    {
      kind: 'tool_call',
      callId: 'call-1',
      toolId: 'files.read',
      hint: 'README.md',
      target: 'README.md',
      at: '2026-05-08T23:55:00.000Z',
    },
    {
      kind: 'tool_result',
      callId: 'call-1',
      toolId: 'files.read',
      ok: true,
      summary: 'Read file README.md.',
      target: 'README.md',
      at: '2026-05-08T23:55:01.000Z',
    },
    { kind: 'text', content: 'Done.' },
  ];

  const collapsed = collapseRenderedMessageParts(parts);

  // thinking + (collapsed call/result) + text = 3
  assert.equal(collapsed.length, 3);
  assert.equal(collapsed[0]?.kind, 'thinking');
  assert.equal(collapsed[1]?.kind, 'tool_result');
  assert.equal(collapsed[2]?.kind, 'text');
});

test('collapseRenderedMessageParts hides tool.batch call rows when the grouped batch result follows', () => {
  const parts: MessagePart[] = [
    {
      kind: 'tool_call',
      callId: 'batch-1',
      toolId: 'tool.batch',
      hint: '{"path":"docs/ARCHITECTURE.md"}',
      target: null,
      at: '2026-05-08T23:55:00.000Z',
    },
    {
      kind: 'tool_batch',
      batchId: 'batch-1',
      label: 'Read 3 files',
      members: [],
      ok: true,
      workspaceRoot: '/Users/copeharder/Programming/CopeNet',
      at: '2026-05-08T23:55:01.000Z',
    },
  ];

  const collapsed = collapseRenderedMessageParts(parts);

  assert.equal(collapsed.length, 1);
  assert.equal(collapsed[0]?.kind, 'tool_batch');
});
