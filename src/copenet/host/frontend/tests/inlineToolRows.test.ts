import assert from 'node:assert/strict';
import test from 'node:test';

import { clipNotice, hasMoreThanShown } from '../src/components/transcript/InlineToolRows';
import type { ToolResultPart } from '../src/types/backend';

function part(overrides: Partial<ToolResultPart> = {}): ToolResultPart {
  return {
    kind: 'tool_result',
    callId: 'c1',
    toolId: 'files.rg',
    ok: true,
    summary: '',
    at: '2026-08-03T00:00:00.000Z',
    ...overrides,
  } as ToolResultPart;
}

test('an overflowed result offers the full output', () => {
  assert.equal(hasMoreThanShown(part({ artifactId: 'artifact-1' })), true);
});

test('a failed call with only an error offers nothing more', () => {
  // Regression: this used to show "Inspect full output" on every failure, which
  // made the button meaningless on the rows where it mattered.
  assert.equal(hasMoreThanShown(part({ ok: false, error: 'path not found' })), false);
});

test('a complete preview offers nothing more', () => {
  assert.equal(
    hasMoreThanShown(part({ preview: { type: 'raw', text: 'all of it' } })),
    false,
  );
  assert.equal(
    hasMoreThanShown(part({
      preview: { type: 'repo_search', query: 'x', matches: [{ path: 'a', line: 1, snippet: 's' }], totalMatches: 1 },
    })),
    false,
  );
});

test('a clipped preview offers the full output', () => {
  assert.equal(
    hasMoreThanShown(part({ preview: { type: 'raw', text: 'clipped', truncated: true, fullChars: 9000 } })),
    true,
  );
  assert.equal(
    hasMoreThanShown(part({
      preview: { type: 'repo_search', query: 'x', matches: [{ path: 'a', line: 1, snippet: 's' }], totalMatches: 189 },
    })),
    true,
  );
  assert.equal(
    hasMoreThanShown(part({
      preview: { type: 'file_read', path: 'a.py', lines: ['one'], startLine: 1, totalLines: 400 },
    })),
    true,
  );
});

test('a clipped preview says how much it is showing', () => {
  assert.equal(
    clipNotice(part({ preview: { type: 'raw', text: 'x'.repeat(4000), truncated: true, fullChars: 107143 } })),
    'Showing 4,000 of 107,143 chars',
  );
  assert.equal(
    clipNotice(part({
      preview: { type: 'repo_search', query: 'def', matches: [{ path: 'a', line: 1, snippet: 's' }], totalMatches: 189 },
    })),
    'Showing 1 of 189 matches',
  );
});

test('a complete preview says nothing — silence means nothing was dropped', () => {
  assert.equal(clipNotice(part({ preview: { type: 'raw', text: 'all of it' } })), null);
  assert.equal(
    clipNotice(part({
      preview: { type: 'repo_search', query: 'x', matches: [{ path: 'a', line: 1, snippet: 's' }], totalMatches: 1 },
    })),
    null,
  );
  assert.equal(clipNotice(part({ ok: false, error: 'boom' })), null);
});
