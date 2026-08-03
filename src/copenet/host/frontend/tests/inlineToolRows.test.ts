import assert from 'node:assert/strict';
import test from 'node:test';

import { hasMoreThanShown } from '../src/components/transcript/InlineToolRows';
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
