import assert from 'node:assert/strict';
import test from 'node:test';

import {
  clampMediaAssetTitle,
  clampResponsiveText,
  getMediaAssetCardBadgeLabel,
  getMobileSectionSummary,
  shouldShowMobileSectionHeader,
} from '../src/lib/mobileCopy';

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

test('getMobileSectionSummary gives short mobile context copy', () => {
  assert.equal(getMobileSectionSummary('home'), 'Workspace pulse and quick starts.');
  assert.equal(getMobileSectionSummary('agents'), 'Sessions, composer, and runtime controls.');
  assert.equal(getMobileSectionSummary('data-tools'), 'Imports, source assets, and utility flows.');
});

test('clampMediaAssetTitle shortens long mobile asset titles', () => {
  const title = 'this-is-a-very-long-media-title-about-a-youtube-video-that-keeps-going-and-going-and-going.mp4';

  assert.equal(clampMediaAssetTitle(title, true), 'this-is-a-very-long-media-title-about-a-youtube-v…');
  assert.equal(clampMediaAssetTitle('Short clip', true), 'Short clip');
});

test('clampMediaAssetTitle trims a human-readable headline earlier on mobile', () => {
  const title = 'Nina Hagen - Naturtrane TopPop appearance from a very long archival upload title';

  assert.equal(clampMediaAssetTitle(title, true), 'Nina Hagen - Naturtrane TopPop appearance from a…');
});

test('mobile media asset badge is removed to preserve width', () => {
  assert.equal(getMediaAssetCardBadgeLabel(true), null);
  assert.equal(getMediaAssetCardBadgeLabel(false), 'Open');
});

test('mobile section header only stays on home', () => {
  assert.equal(shouldShowMobileSectionHeader('home'), true);
  assert.equal(shouldShowMobileSectionHeader('agents'), false);
  assert.equal(shouldShowMobileSectionHeader('data-tools'), false);
});
