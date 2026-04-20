import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';

import { MobileBottomNav } from '../src/components/mobile/MobileNav';
import { useAppStore } from '../src/store/useAppStore';

test('mobile bottom nav renders the primary phone sections', () => {
  useAppStore.setState({
    currentSection: 'workflows',
    mobileOverflowOpen: false,
  });

  const html = renderToStaticMarkup(<MobileBottomNav />);

  assert.match(html, /aria-label=\"Home\"/);
  assert.match(html, /aria-label=\"Agents\"/);
  assert.match(html, /aria-label=\"Workflows\"/);
  assert.match(html, /aria-label=\"Media\"/);
  assert.match(html, /aria-label=\"More\"/);
});
