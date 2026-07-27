import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';

import { GatewayTokenForm } from '../src/components/ConnectionBanner';

test('authentication failure offers a private token entry form', () => {
  const html = renderToStaticMarkup(<GatewayTokenForm authError="invalid token" />);

  assert.match(html, /invalid token/);
  assert.match(html, /type="password"/);
  assert.match(html, /Gateway token/);
  assert.match(html, /Save &amp; reconnect/);
  assert.doesNotMatch(html, /token=/);
});
