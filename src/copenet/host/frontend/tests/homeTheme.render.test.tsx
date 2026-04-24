import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

import { HomePage } from '../src/components/HomePage';
import { useAppStore } from '../src/store/useAppStore';

test('home hero switches to cinematic dark art direction in dark mode', () => {
  useAppStore.setState({
    themeMode: 'dark',
    sessions: [],
    messages: {},
    providers: [],
    tools: [],
    wsStatus: 'connected',
  });

  const html = renderToStaticMarkup(<HomePage />);

  assert.match(html, /data-home-hero=\"cinematic-dark\"/);
});

test('home hero stays on the default treatment in light mode', () => {
  useAppStore.setState({
    themeMode: 'light',
    sessions: [],
    messages: {},
    providers: [],
    tools: [],
    wsStatus: 'connected',
  });

  const html = renderToStaticMarkup(<HomePage />);

  assert.doesNotMatch(html, /data-home-hero=\"cinematic-dark\"/);
});
