import test from 'node:test';
import assert from 'node:assert/strict';

import { copyTextToClipboard } from '../src/lib/clipboard';

function replaceGlobal(name: 'navigator' | 'document', value: unknown): () => void {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, { configurable: true, value });
  return () => {
    if (descriptor) Object.defineProperty(globalThis, name, descriptor);
    else delete (globalThis as Record<string, unknown>)[name];
  };
}

test('copyTextToClipboard uses the async Clipboard API when available', async () => {
  let copied = '';
  const restoreNavigator = replaceGlobal('navigator', {
    clipboard: {
      writeText: async (text: string) => {
        copied = text;
      },
    },
  });
  const restoreDocument = replaceGlobal('document', undefined);

  try {
    await copyTextToClipboard('hello');
    assert.equal(copied, 'hello');
  } finally {
    restoreDocument();
    restoreNavigator();
  }
});

test('copyTextToClipboard falls back to selection copy when Clipboard API is missing', async () => {
  let textarea: Record<string, unknown> | null = null;
  let copied = false;
  const restoreNavigator = replaceGlobal('navigator', {});
  const restoreDocument = replaceGlobal('document', {
    activeElement: null,
    body: {
      appendChild: (node: Record<string, unknown>) => {
        textarea = node;
      },
    },
    createElement: () => ({
      value: '',
      readOnly: false,
      style: {},
      setAttribute: () => undefined,
      focus: () => undefined,
      select: () => undefined,
      setSelectionRange: () => undefined,
      remove: () => undefined,
    }),
    execCommand: (command: string) => {
      copied = command === 'copy';
      return copied;
    },
    getSelection: () => null,
  });

  try {
    await copyTextToClipboard('fallback');
    assert.equal(textarea?.value, 'fallback');
    assert.equal(copied, true);
  } finally {
    restoreDocument();
    restoreNavigator();
  }
});

test('copyTextToClipboard falls back when the Clipboard API rejects', async () => {
  let fallbackUsed = false;
  const restoreNavigator = replaceGlobal('navigator', {
    clipboard: {
      writeText: async () => {
        throw new Error('permission denied');
      },
    },
  });
  const restoreDocument = replaceGlobal('document', {
    activeElement: null,
    body: { appendChild: () => undefined },
    createElement: () => ({
      value: '',
      readOnly: false,
      style: {},
      setAttribute: () => undefined,
      focus: () => undefined,
      select: () => undefined,
      setSelectionRange: () => undefined,
      remove: () => undefined,
    }),
    execCommand: () => {
      fallbackUsed = true;
      return true;
    },
    getSelection: () => null,
  });

  try {
    await copyTextToClipboard('fallback after rejection');
    assert.equal(fallbackUsed, true);
  } finally {
    restoreDocument();
    restoreNavigator();
  }
});

test('copyTextToClipboard reports an actionable error when no copy path works', async () => {
  const restoreNavigator = replaceGlobal('navigator', {});
  const restoreDocument = replaceGlobal('document', undefined);

  try {
    await assert.rejects(copyTextToClipboard('nope'), /Clipboard access is unavailable/);
  } finally {
    restoreDocument();
    restoreNavigator();
  }
});
