import assert from 'node:assert/strict';
import test from 'node:test';
import { shouldSubmitComposerOnEnter } from '../src/components/agents/composerKeyboard';

test('desktop Enter submits the composer', () => {
  assert.equal(shouldSubmitComposerOnEnter({
    key: 'Enter',
    shiftKey: false,
    isComposing: false,
    isMobile: false,
  }), true);
});

test('mobile Return inserts a line break instead of submitting', () => {
  assert.equal(shouldSubmitComposerOnEnter({
    key: 'Enter',
    shiftKey: false,
    isComposing: false,
    isMobile: true,
  }), false);
});

test('Shift+Enter and IME composition never submit', () => {
  assert.equal(shouldSubmitComposerOnEnter({
    key: 'Enter',
    shiftKey: true,
    isComposing: false,
    isMobile: false,
  }), false);
  assert.equal(shouldSubmitComposerOnEnter({
    key: 'Enter',
    shiftKey: false,
    isComposing: true,
    isMobile: false,
  }), false);
});
