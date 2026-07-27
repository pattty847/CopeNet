import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';

import { ComposerToolPickerButton } from '../src/components/agents/ComposerToolControls';
import { useAppStore } from '../src/store/useAppStore';

test('composer tool picker stays available only below the desktop inspector breakpoint', () => {
  useAppStore.setState({ composerRequestedToolIds: {} });

  const html = renderToStaticMarkup(
    <ComposerToolPickerButton composerKey="responsive-picker-test" />,
  );

  assert.match(html, /class="relative lg:hidden"/);
  assert.match(html, /aria-label="Attach tools"/);
});
