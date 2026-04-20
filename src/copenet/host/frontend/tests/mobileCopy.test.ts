import assert from 'node:assert/strict';
import test from 'node:test';

import { clampResponsiveText } from '../src/lib/mobileCopy';

test('clampResponsiveText truncates earlier on mobile', () => {
  const text = 'Inspect the repository with tools, then summarize where a runtime state can drift after resume.';

  assert.equal(clampResponsiveText(text, { isMobile: true, mobileLimit: 24, desktopLimit: 120 }), 'Inspect the repository…');
  assert.equal(clampResponsiveText(text, { isMobile: false, mobileLimit: 24, desktopLimit: 120 }), text);
});

test('clampResponsiveText preserves short strings', () => {
  assert.equal(
    clampResponsiveText('files.read', { isMobile: true, mobileLimit: 24, desktopLimit: 40 }),
    'files.read',
  );
});
