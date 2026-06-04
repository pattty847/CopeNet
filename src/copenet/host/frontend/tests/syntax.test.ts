import test from 'node:test';
import assert from 'node:assert/strict';

import { tokenizeLine, langFromPath } from '../src/lib/syntax';

function classes(line: string, lang = '') {
  return tokenizeLine(line, lang).map((t) => `${t.cls}:${t.text}`);
}

test('tokenizes keywords, strings, and identifiers', () => {
  const toks = tokenizeLine('return "Hello, " + name', 'py');
  // keyword `return`, a string literal, plus plain text
  assert.ok(toks.some((t) => t.cls === 'keyword' && t.text === 'return'));
  assert.ok(toks.some((t) => t.cls === 'string' && t.text === '"Hello, "'));
  assert.ok(toks.some((t) => t.cls === 'plain' && t.text.includes('name')));
});

test('python # comment is a comment, // is not (lang-aware)', () => {
  assert.ok(tokenizeLine('x = 1  # set x', 'py').some((t) => t.cls === 'comment' && t.text === '# set x'));
  // in JS, # is not a comment marker
  assert.ok(!tokenizeLine('a // b', 'js').some((t) => t.cls === 'comment' && t.text.startsWith('#')));
  assert.ok(tokenizeLine('a // b', 'js').some((t) => t.cls === 'comment' && t.text === '// b'));
});

test('numbers are detected but not inside identifiers', () => {
  assert.ok(tokenizeLine('const x = 42', 'ts').some((t) => t.cls === 'number' && t.text === '42'));
  // foo2 is an identifier, not foo + number 2
  assert.ok(!tokenizeLine('foo2 = 1', 'ts').some((t) => t.cls === 'number' && t.text === '2'));
});

test('string with escaped quote stays one token', () => {
  const toks = tokenizeLine('x = "a\\"b"', 'js');
  assert.ok(toks.some((t) => t.cls === 'string' && t.text === '"a\\"b"'));
});

test('reconstructing tokens yields the original line', () => {
  const line = 'def greet(name):  # greet someone';
  const joined = tokenizeLine(line, 'py').map((t) => t.text).join('');
  assert.equal(joined, line);
});

test('langFromPath extracts the extension', () => {
  assert.equal(langFromPath('src/copenet/app.py'), 'py');
  assert.equal(langFromPath('a/b/main.tsx'), 'tsx');
  assert.equal(langFromPath('Makefile'), 'makefile');
});
