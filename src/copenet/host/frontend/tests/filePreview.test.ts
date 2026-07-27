import test from 'node:test';
import assert from 'node:assert/strict';

import { physicalFilePreviewLines } from '../src/lib/filePreview';

test('splits embedded and Windows newlines into physical source lines', () => {
  assert.deepEqual(
    physicalFilePreviewLines(['one\ntwo', 'three\r\nfour']),
    ['one', 'two', 'three', 'four'],
  );
});

test('preserves intentional blank source lines and applies the physical-line limit', () => {
  assert.deepEqual(physicalFilePreviewLines('one\n\nthree', 2), ['one', '']);
});

test('returns no preview rows when a payload has no line content', () => {
  assert.deepEqual(physicalFilePreviewLines(undefined), []);
});
