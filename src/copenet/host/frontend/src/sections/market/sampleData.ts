// Illustrative Market Monitor data — seeded with Patrick's real watchlist + roles.
// THIS IS NOT REAL MARKET DATA. Every panel ships with status:'preview' so the UI shows the
// "Preview · illustrative" badge until Codex's backend flips it to 'live' (blueprint §1, §3).
// When the seam (useMarketMonitorData) swaps to real market.* RPCs, this file is no longer imported.

import type { DashboardPayload, TickerDetailPayload, UniverseAsset } from './types';

export const SAMPLE_UNIVERSE: UniverseAsset[] = [
  // Portfolio (held)
  { symbol: 'ASX', name: 'ASE Technology Holding', role: 'holding' },
  { symbol: 'GOOG', name: 'Alphabet Class C', role: 'holding' },
  { symbol: 'SOFI', name: 'SoFi Technologies', role: 'holding' },
  { symbol: 'VTI', name: 'Vanguard Total Stock Market', role: 'holding' },
  { symbol: 'XLK', name: 'Technology Select Sector', role: 'holding' },
  { symbol: 'XLE', name: 'Energy Select Sector', role: 'holding' },
  { symbol: 'SLI', name: 'Standard Lithium', role: 'holding' },
  // Major markets (benchmark / macro)
  { symbol: 'VOO', name: 'Vanguard S&P 500', role: 'index' },
  { symbol: 'QQQ', name: 'Invesco QQQ Trust', role: 'index' },
  { symbol: 'VOOG', name: 'Vanguard S&P 500 Growth', role: 'index' },
  { symbol: 'DXY', name: 'U.S. Dollar Index', role: 'macro' },
  { symbol: 'VIX', name: 'Volatility Index', role: 'macro' },
  { symbol: 'BTCUSD', name: 'Bitcoin / USD', role: 'macro' },
  { symbol: 'ETHUSD', name: 'Ethereum / USD', role: 'macro' },
  // Watch
  { symbol: 'CRWV', name: 'CoreWeave', role: 'watch' },
  { symbol: 'SHLD', name: 'Global X Defense Tech', role: 'watch' },
  { symbol: 'PLD', name: 'Prologis', role: 'watch' },
  // Future bags
  { symbol: 'AMZN', name: 'Amazon', role: 'watch' },
  { symbol: 'INTC', name: 'Intel', role: 'watch' },
  { symbol: 'IWM', name: 'iShares Russell 2000', role: 'index' },
  { symbol: 'NVDA', name: 'NVIDIA', role: 'watch' },
  { symbol: 'TSLA', name: 'Tesla', role: 'watch' },
  { symbol: 'SPCX', name: 'SpaceX', role: 'watch' },
  // Sectors
  { symbol: 'XLRE', name: 'Real Estate', role: 'sector' },
  { symbol: 'SMH', name: 'Semiconductors', role: 'sector' },
  { symbol: 'XLI', name: 'Industrials', role: 'sector' },
  { symbol: 'XLF', name: 'Financials', role: 'sector' },
  { symbol: 'XLP', name: 'Consumer Staples', role: 'sector' },
  { symbol: 'XLY', name: 'Consumer Discretionary', role: 'sector' },
  { symbol: 'XLU', name: 'Utilities', role: 'sector' },
  { symbol: 'XLB', name: 'Materials', role: 'sector' },
  { symbol: 'XLV', name: 'Health Care', role: 'sector' },
  { symbol: 'XLC', name: 'Communication Services', role: 'sector' },
];

const spark = (dir: number): number[] => {
  // deterministic little 22-pt walk so previews are stable across renders
  const v: number[] = [];
  let cur = 0.5;
  let h = 1234567;
  for (let i = 0; i < 22; i++) {
    h = (h * 1103515245 + 12345) & 0x7fffffff;
    cur += ((h / 0x7fffffff) - 0.5) * 0.22 + dir * 0.012;
    v.push(cur);
  }
  return v;
};

export const SAMPLE_DASHBOARD: DashboardPayload = {
  asOf: 'illustrative — as of last close',
  briefing: {
    status: 'preview',
    data: {
      headline: 'The tape is constructive — breadth is widening and credit stays calm. Not euphoric.',
      emphasis: 'constructive',
      summary:
        'Money is rotating out of defensives and into semis & cyclicals. A few things want your attention. None of this is a forecast — it is a read on the weight of evidence, with caveats on each call.',
      changed: [
        { text: 'chop → risk-on', tone: 'up' },
        { text: 'XLK crossed into Leading', tone: 'up' },
        { text: 'VIX −2.1', tone: 'up' },
      ],
      attention: [
        { kind: 'Entered add-zone', label: 'PLD · −9% below 50W MA', glyph: '◇', symbol: 'PLD' },
        { kind: 'Weekly trend change', label: 'SOFI · confirmed daily', glyph: '↑', symbol: 'SOFI' },
        { kind: 'Insider cluster-buy', label: 'INTC · 3 insiders', glyph: '▲', symbol: 'INTC' },
      ],
      vix: 14.8,
      breadthPct: 68,
    },
  },
  regime: {
    status: 'preview',
    data: {
      current: 'risk-on',
      scale: [
        { name: 'Risk-off', active: false },
        { name: 'Chop', active: false },
        { name: 'Risk-on', active: true, note: 'now' },
        { name: 'Event-risk', active: false, note: 'CPI Thu' },
      ],
    },
  },
  macro: {
    status: 'preview',
    data: [
      { label: 'DXY', value: '98.42', change: '+0.31%', tone: 'up', spark: spark(1) },
      { label: 'US 10Y', value: '4.21%', change: '−3 bps', tone: 'down', spark: spark(-1) },
      { label: 'VIX', value: '14.8', change: '−0.6', tone: 'down', spark: spark(-1) },
      { label: 'Gold', value: '$3,340', change: '+0.4%', tone: 'up', spark: spark(1) },
      { label: 'WTI Oil', value: '$71.2', change: '−1.1%', tone: 'down', spark: spark(-1) },
      { label: 'BTC', value: '$64,210', change: '+2.3%', tone: 'up', spark: spark(1) },
      { label: 'ETH', value: '$3,182', change: '+1.8%', tone: 'up', spark: spark(1) },
    ],
  },
  rrg: {
    status: 'preview',
    data: [
      { symbol: 'SMH', name: 'Semiconductors', quadrant: 'leading', tail: [{ x: 1.2, y: 0.4 }, { x: 2.1, y: 0.9 }, { x: 3.1, y: 1.2 }, { x: 4.0, y: 1.0 }] },
      { symbol: 'XLK', name: 'Technology', quadrant: 'leading', tail: [{ x: 0.8, y: 0.2 }, { x: 1.6, y: 0.7 }, { x: 2.4, y: 1.1 }, { x: 3.1, y: 1.0 }] },
      { symbol: 'XLF', name: 'Financials', quadrant: 'weakening', tail: [{ x: 3.4, y: 1.2 }, { x: 3.6, y: 0.5 }, { x: 3.4, y: -0.2 }, { x: 3.2, y: -0.6 }] },
      { symbol: 'XLE', name: 'Energy', quadrant: 'improving', tail: [{ x: -4.0, y: -1.2 }, { x: -3.4, y: -0.2 }, { x: -2.8, y: 0.6 }, { x: -2.2, y: 1.1 }] },
      { symbol: 'XLU', name: 'Utilities', quadrant: 'lagging', tail: [{ x: -2.2, y: 0.4 }, { x: -2.6, y: -0.2 }, { x: -3.0, y: -0.8 }, { x: -3.3, y: -1.1 }] },
      { symbol: 'XLV', name: 'Health Care', quadrant: 'improving', tail: [{ x: -2.6, y: -0.8 }, { x: -2.2, y: -0.1 }, { x: -1.8, y: 0.6 }, { x: -1.3, y: 1.0 }] },
      { symbol: 'XLC', name: 'Communication Services', quadrant: 'leading', tail: [{ x: 0.6, y: 0.3 }, { x: 1.3, y: 0.8 }, { x: 2.0, y: 1.0 }, { x: 2.6, y: 0.8 }] },
    ],
  },
  accumulation: {
    status: 'preview',
    data: [
      { symbol: 'PLD', name: 'Prologis', belowMa: '−9.0%', drawdown: '−34%', rsi: '34', confluence: 3, why: 'Quality logistics REIT at multi-year support; first daily higher-low forming.' },
      { symbol: 'INTC', name: 'Intel', belowMa: '−5.1%', drawdown: '−58%', rsi: '36', confluence: 3, why: 'Turnaround optionality; insider cluster-buy this week, stabilizing above prior lows.' },
      { symbol: 'AMZN', name: 'Amazon', belowMa: '−4.2%', drawdown: '−21%', rsi: '41', confluence: 2, why: 'Megacap pullback near the 50-week; retail margin inflecting.' },
      { symbol: 'SLI', name: 'Standard Lithium', belowMa: '−18.0%', drawdown: '−72%', rsi: '39', confluence: 1, why: 'Deep value, but weekly trend has not turned — watch only.' },
    ],
  },
  trend: {
    status: 'preview',
    data: [
      { symbol: 'SOFI', direction: 'up', note: 'Weekly up — confirmed daily', when: 'Fri', confirmed: true },
      { symbol: 'XLE', direction: 'up', note: 'Weekly up — confirmed daily', when: 'Wed', confirmed: true },
      { symbol: 'TSLA', direction: 'down', note: 'Weekly down — caution flag', when: 'Thu', confirmed: true },
    ],
  },
  portfolio: {
    status: 'preview',
    data: {
      total: '$—',
      pnl: 'cost basis pending',
      pnlTone: 'flat',
      positions: [
        { symbol: 'GOOG', shares: 0, avgCost: 0, last: '—', pnlPct: '—', tone: 'flat', nudge: '' },
        { symbol: 'ASX', shares: 0, avgCost: 0, last: '—', pnlPct: '—', tone: 'flat', nudge: '' },
        { symbol: 'SOFI', shares: 0, avgCost: 0, last: '—', pnlPct: '—', tone: 'flat', nudge: '' },
        { symbol: 'VTI', shares: 0, avgCost: 0, last: '—', pnlPct: '—', tone: 'flat', nudge: '' },
        { symbol: 'XLK', shares: 0, avgCost: 0, last: '—', pnlPct: '—', tone: 'flat', nudge: '' },
        { symbol: 'XLE', shares: 0, avgCost: 0, last: '—', pnlPct: '—', tone: 'flat', nudge: '' },
      ],
    },
  },
  speculative: {
    status: 'preview',
    data: [
      { symbol: 'SOFI', pnlPct: '—', tone: 'flat', thesis: 'Fintech re-rate. Sized small — defined exit.', entry: '—', target: '—', invalidation: '—' },
      { symbol: 'SLI', pnlPct: '—', tone: 'flat', thesis: 'Lithium optionality. Hail-mary sizing only.', entry: '—', target: '—', invalidation: '—' },
    ],
  },
  evidence: {
    status: 'preview',
    data: [
      { type: 'Insider', symbol: 'INTC', headline: '3 insiders bought — cluster buy', source: 'Form 4 · 2d', tone: 'up' },
      { type: '8-K', symbol: 'GOOG', headline: 'Board authorizes additional buyback', source: 'SEC · 1d', tone: 'flat' },
      { type: 'News', symbol: 'NVDA', headline: 'Datacenter demand commentary stays strong', source: 'Reuters · 4h', tone: 'flat' },
      { type: 'Insider', symbol: 'SOFI', headline: 'Director open-market purchase', source: 'Form 4 · 3d', tone: 'up' },
    ],
  },
  contrarian: {
    status: 'preview',
    data: [
      { signal: 'PLD accumulation', kill: 'Wrong if rates push higher — REIT cap rates re-rate and one higher-low is not a weekly turn.' },
      { signal: 'SOFI trend change', kill: 'Wrong if consumer-credit charge-offs tick up. One weekly close above trend ≠ a trend.' },
      { signal: 'Risk-on regime', kill: 'Wrong if the 10-year breaks 4.6% — that pressures the multiple expansion driving this tape.' },
    ],
  },
};

export function sampleTicker(symbol: string): TickerDetailPayload {
  const name = SAMPLE_UNIVERSE.find((a) => a.symbol === symbol)?.name ?? symbol;
  return {
    symbol,
    name,
    last: '—',
    change: '—',
    tone: 'flat',
    series: { daily: [], weekly: [], monthly: [] },
    verdict: [
      { bench: 'VOO', label: 'In line', pct: '50%', tone: 'flat' },
      { bench: 'Sector', label: 'In line', pct: '50%', tone: 'flat' },
    ],
    signals: [
      { key: 'Weekly trend', value: '—', tone: 'flat' },
      { key: 'Daily confirm', value: '—', tone: 'flat' },
      { key: 'vs 50W MA', value: '—', tone: 'flat' },
      { key: 'RSI (14W)', value: '—', tone: 'flat' },
      { key: 'Drawdown', value: '—', tone: 'flat' },
      { key: 'Rel-strength rank', value: '—', tone: 'flat' },
    ],
    evidence: [],
    events: [],
    kill: 'Illustrative preview — real signals and evidence land when the backend is wired.',
  };
}
