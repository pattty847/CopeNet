import test from 'node:test';
import assert from 'node:assert/strict';

import { parseUnifiedDiff, diffGutterWidth } from '../src/lib/diff';

const SAMPLE = [
  '--- a/sample.txt',
  '+++ b/sample.txt',
  '@@ -1,3 +1,3 @@',
  '-hello world',
  '+hello CopeNet',
  ' this is line two',
  ' line three here',
].join('\n');

test('parseUnifiedDiff skips file headers and parses a hunk', () => {
  const rows = parseUnifiedDiff(SAMPLE);
  // file headers (---/+++) dropped; hunk + 4 content rows remain
  assert.equal(rows.length, 5);
  assert.equal(rows[0].kind, 'hunk');
});

test('parseUnifiedDiff assigns real old/new line numbers from the hunk header', () => {
  const rows = parseUnifiedDiff(SAMPLE).filter((r) => r.kind !== 'hunk');
  // -hello world : removed -> old line 1, no new
  assert.deepEqual({ kind: rows[0].kind, oldNo: rows[0].oldNo, newNo: rows[0].newNo }, { kind: 'del', oldNo: 1, newNo: null });
  // +hello CopeNet : added -> new line 1, no old
  assert.deepEqual({ kind: rows[1].kind, oldNo: rows[1].oldNo, newNo: rows[1].newNo }, { kind: 'add', oldNo: null, newNo: 1 });
  // context lines advance both counters
  assert.deepEqual({ kind: rows[2].kind, oldNo: rows[2].oldNo, newNo: rows[2].newNo }, { kind: 'context', oldNo: 2, newNo: 2 });
  assert.deepEqual({ kind: rows[3].kind, oldNo: rows[3].oldNo, newNo: rows[3].newNo }, { kind: 'context', oldNo: 3, newNo: 3 });
});

test('parseUnifiedDiff strips the +/-/space marker from text', () => {
  const rows = parseUnifiedDiff(SAMPLE).filter((r) => r.kind !== 'hunk');
  assert.equal(rows[0].text, 'hello world');
  assert.equal(rows[1].text, 'hello CopeNet');
  assert.equal(rows[2].text, 'this is line two');
});

test('parseUnifiedDiff handles a multi-line addition advancing only new numbers', () => {
  const diff = ['@@ -5,2 +5,4 @@', ' ctx a', '+added one', '+added two', ' ctx b'].join('\n');
  const rows = parseUnifiedDiff(diff).filter((r) => r.kind !== 'hunk');
  assert.deepEqual(rows.map((r) => [r.kind, r.oldNo, r.newNo]), [
    ['context', 5, 5],
    ['add', null, 6],
    ['add', null, 7],
    ['context', 6, 8],
  ]);
});

test('diffGutterWidth sizes to the widest line number', () => {
  const rows = parseUnifiedDiff(['@@ -98,1 +98,1 @@', '-a', '+b'].join('\n'));
  assert.equal(diffGutterWidth(rows), 2); // "98"
});

test('parseUnifiedDiff returns empty for empty input', () => {
  assert.deepEqual(parseUnifiedDiff(''), []);
});
