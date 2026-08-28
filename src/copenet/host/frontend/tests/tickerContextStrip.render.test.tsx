import assert from 'node:assert/strict';
import test from 'node:test';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { TickerContextStrip } from '../src/sections/market/TickerContextStrip';
import type { EvidenceItem, TickerDetailPayload, TickerIntelligence } from '../src/sections/market/types';

const intelligence: TickerIntelligence = {
  assetRole: 'Large-cap technology',
  trend: { longTrend: 'Uptrend' },
  momentum: {},
  returns: {},
  drawdown: { drawdown52wPct: -8.4 },
  volatility: {},
  relativeStrength: { benchmarks: [] },
  structure: {},
  dataQuality: { historyWeeks: 520, hasVolume: true, thinHistory: false },
  portfolio: null,
};

const detail = {
  symbol: 'TEST',
  name: 'Synthetic Test Asset',
  intelligence,
} as TickerDetailPayload;

const evidence: EvidenceItem[] = [{
  type: '8-K',
  symbol: 'TEST',
  headline: 'Synthetic material event',
  source: 'Synthetic fixture',
  tone: 'flat',
  t: 1_750_000_000,
}];

test('ticker context exposes evidence, regime, and data status without inventing a position', () => {
  const html = renderToStaticMarkup(<TickerContextStrip detail={detail} evidence={evidence} onOpenTab={() => undefined} />);

  assert.match(html, /Latest material evidence/);
  assert.match(html, /Synthetic material event/);
  assert.match(html, /Uptrend · 8\.4% off 52w high/);
  assert.match(html, /Price, SEC, and fundamentals current/);
  assert.doesNotMatch(html, /<small>Position<\/small>/);
});

test('ticker context reveals an actual held position', () => {
  const heldDetail = {
    ...detail,
    intelligence: {
      ...intelligence,
      portfolio: { shares: 12, pnlPct: 4.2, source: 'synthetic' },
    },
  } as TickerDetailPayload;
  const html = renderToStaticMarkup(<TickerContextStrip detail={heldDetail} evidence={[]} onOpenTab={() => undefined} />);

  assert.match(html, /<small>Position<\/small>/);
  assert.match(html, /12 shares · \+4\.2%/);
});
