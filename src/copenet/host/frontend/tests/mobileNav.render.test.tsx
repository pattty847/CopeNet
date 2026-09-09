import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { MobileBottomNav } from '../src/components/mobile/MobileNav';
import { useAppStore } from '../src/store/useAppStore';

test('mobile bottom nav renders the primary phone sections', () => {
  useAppStore.setState({
    currentSection: 'market',
    mobileOverflowOpen: false,
  });

  const html = renderToStaticMarkup(<MobileBottomNav />);

  assert.match(html, /aria-label="Home"/);
  assert.match(html, /aria-label="Market"/);
  assert.match(html, /aria-label="Agents"/);
  assert.match(html, /aria-label="Runs"/);
  assert.match(html, /aria-label="More"/);
  assert.match(html, />Home</);
  assert.match(html, />Market</);
  assert.match(html, />Agents</);
});

test('workflows and experiments are reachable from the overflow sheet, not the bar', () => {
  useAppStore.setState({ currentSection: 'home', mobileOverflowOpen: false });

  const html = renderToStaticMarkup(<MobileBottomNav />);

  assert.doesNotMatch(html, /aria-label="Workflows"/);
  assert.doesNotMatch(html, /aria-label="Experiments"/);
});
