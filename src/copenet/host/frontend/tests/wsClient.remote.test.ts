import assert from 'node:assert/strict';
import test from 'node:test';

test('ws client module can load without a browser window for server-side/mobile test contexts', async () => {
  const previousWindow = (globalThis as any).window;
  const previousDocument = (globalThis as any).document;

  try {
    delete (globalThis as any).window;
    delete (globalThis as any).document;

    const mod = await import('../src/lib/wsClient');
    assert.ok(mod.wsClient);
  } finally {
    if (previousWindow !== undefined) {
      (globalThis as any).window = previousWindow;
    }
    if (previousDocument !== undefined) {
      (globalThis as any).document = previousDocument;
    }
  }
});
