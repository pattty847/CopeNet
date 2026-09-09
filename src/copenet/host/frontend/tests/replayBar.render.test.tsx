import assert from 'node:assert/strict';
import test from 'node:test';
import { renderToStaticMarkup } from 'react-dom/server';

import { ReplayBar } from '../src/sections/market/replay/ReplayBar';
import type { ChartReplay } from '../src/sections/market/replay/useChartReplay';

function replay(overrides: Partial<ChartReplay> = {}): ChartReplay {
  const noop = () => {};
  return {
    active: true, playing: false, speed: 1, index: 41, cursorTime: Date.UTC(2024, 6, 14) / 1000,
    total: 260, atStart: false, atEnd: false,
    enter: noop, exit: noop, toggle: noop, play: noop, pause: noop, togglePlay: noop,
    step: noop, seek: noop, toStart: noop, toEnd: noop, setSpeed: noop, nudgeSpeed: noop,
    ...overrides,
  };
}

test('the transport reports the cursor bar, its date and how far through the range it is', () => {
  const html = renderToStaticMarkup(<ReplayBar replay={replay()} />);
  assert.match(html, /Jul 14, 2024/);
  assert.match(html, /42 \/ 260/, 'position is 1-based — bar 42 of 260, not index 41');
  assert.match(html, /aria-label="Play replay"/);
  assert.match(html, /1×/);
  assert.match(html, /max="259"/);
});

test('the transport disables only the directions that have run out', () => {
  const atStart = renderToStaticMarkup(<ReplayBar replay={replay({ index: 0, atStart: true })} />);
  assert.match(atStart, /aria-label="Previous bar" disabled/);
  assert.doesNotMatch(atStart, /aria-label="Next bar" disabled/);

  const atEnd = renderToStaticMarkup(<ReplayBar replay={replay({ index: 259, atEnd: true })} />);
  assert.match(atEnd, /aria-label="Next bar" disabled/);
  assert.doesNotMatch(atEnd, /aria-label="Previous bar" disabled/);
});

test('speed nudges stop at the ends of the preset ladder', () => {
  assert.match(renderToStaticMarkup(<ReplayBar replay={replay({ speed: 0.25 })} />), /aria-label="Slower" disabled/);
  assert.match(renderToStaticMarkup(<ReplayBar replay={replay({ speed: 16 })} />), /aria-label="Faster" disabled/);
  assert.doesNotMatch(renderToStaticMarkup(<ReplayBar replay={replay({ speed: 2 })} />), /aria-label="(Slower|Faster)" disabled/);
});

test('the strip is absent when replay is off or there is nothing to walk', () => {
  assert.equal(renderToStaticMarkup(<ReplayBar replay={replay({ active: false })} />), '');
  assert.equal(renderToStaticMarkup(<ReplayBar replay={replay({ total: 0 })} />), '');
});

test('playing swaps the transport to pause so the button never lies about the state', () => {
  const html = renderToStaticMarkup(<ReplayBar replay={replay({ playing: true })} />);
  assert.match(html, /aria-label="Pause replay"/);
  assert.doesNotMatch(html, /aria-label="Play replay"/);
});
