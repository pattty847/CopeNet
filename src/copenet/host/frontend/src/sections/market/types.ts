// Market Monitor — shared data contract.
// Source of truth: docs/plans/MARKET_MONITOR_BUILD_BLUEPRINT.md §2.
// The backend (Codex) emits JSON matching these shapes via the market.* RPCs;
// the frontend consumes them through useMarketMonitorData(). Keep in sync with the blueprint.

export type Tone = 'up' | 'down' | 'flat'; // drives green / red / muted ONLY
export type Direction = 'up' | 'down';
export type AssetRole = 'index' | 'holding' | 'watch' | 'trend' | 'spec' | 'sector' | 'macro';

export type PanelStatus = 'live' | 'preview' | 'stale' | 'error';

/** Every panel's data is wrapped so we can ship honestly and flip panels to `live` one at a time. */
export interface Panel<T> {
  status: PanelStatus;
  data: T;
  asOf?: string;
  note?: string;
}

export interface UniverseAsset {
  symbol: string;
  name: string;
  role: AssetRole;
}

// ---------- dashboard ----------
export interface AttentionItem {
  kind: string;
  label: string;
  glyph: string;
  symbol: string;
}

export interface Briefing {
  headline: string;
  emphasis?: string; // substring of headline to amber-highlight
  summary: string;
  changed: { text: string; tone: Tone }[];
  attention: AttentionItem[];
  vix: number;
  breadthPct: number;
}

export interface Regime {
  current: 'risk-off' | 'chop' | 'risk-on' | 'event-risk';
  scale: { name: string; active: boolean; note?: string }[];
}

export interface MacroItem {
  label: string;
  value: string;
  change: string;
  tone: Tone;
  spark: number[];
}

export interface RrgSector {
  symbol: string;
  name: string;
  tail: { x: number; y: number }[]; // x = RS-Ratio, y = RS-Momentum; last point = current
  quadrant: 'leading' | 'weakening' | 'lagging' | 'improving';
}

export interface AccumulationRow {
  symbol: string;
  name: string;
  belowMa: string;
  drawdown: string;
  rsi: string;
  confluence: number; // 0..4
  why: string;
}

export interface TrendRow {
  symbol: string;
  direction: Direction;
  note: string;
  when: string;
  confirmed: boolean;
}

export interface PortfolioPosition {
  symbol: string;
  shares: number;
  avgCost: number;
  last: string;
  pnlPct: string;
  tone: Tone;
  nudge?: string;
}

export interface Portfolio {
  total: string;
  pnl: string;
  pnlTone: Tone;
  positions: PortfolioPosition[];
}

export interface SpecPosition {
  symbol: string;
  pnlPct: string;
  tone: Tone;
  thesis: string;
  entry: string;
  target: string;
  invalidation: string;
}

export interface EvidenceItem {
  type: 'Insider' | '8-K' | 'News';
  symbol: string;
  headline: string;
  source: string;
  tone: Tone;
  url?: string;
}

export interface ContrarianNote {
  signal: string;
  kill: string;
}

export interface SoftBottomItem {
  symbol: string;
  name: string;
  score: number;
  drawdown: string;
  rsi: string;
}

export interface DashboardPayload {
  asOf: string;
  briefing: Panel<Briefing>;
  regime: Panel<Regime>;
  macro: Panel<MacroItem[]>;
  rrg: Panel<RrgSector[]>;
  accumulation: Panel<AccumulationRow[]>;
  trend: Panel<TrendRow[]>;
  softBottoming: Panel<SoftBottomItem[]>;
  portfolio: Panel<Portfolio>;
  speculative: Panel<SpecPosition[]>;
  evidence: Panel<EvidenceItem[]>;
  contrarian: Panel<ContrarianNote[]>;
}

// ---------- ticker detail ----------
export interface Ohlcv {
  t: number;
  o: number;
  h: number;
  l: number;
  c: number;
  v: number;
}

export interface VerdictRow {
  bench: string;
  label: 'Beats' | 'Lags' | 'In line';
  pct: string;
  tone: Tone;
}

export interface SignalRow {
  key: string;
  value: string;
  tone: Tone;
}

export interface ChartEvent {
  t: number;
  kind: 'insider' | '8-K';
  glyph: string;
}

// ---------- model reads (Insight Engine Phase D) ----------
export interface MarketRead {
  headline: string;
  emphasis: string;
  summary: string;
  regime: 'risk-off' | 'chop' | 'risk-on' | 'event-risk';
  regimeReasoning: string;
  attention: { symbol: string; kind: string; why: string }[];
  rotationRead: string;
  speculativeComment: string;
  thesisKillers: { signal: string; kill: string }[];
  caveats: string;
  model: string;
  generatedAt: string;
}

export interface TickerRead {
  read: string;
  bullCase: string;
  bearCase: string;
  whatWouldChangeMyMind: string;
  confidence: 'low' | 'medium' | 'high';
  confidenceReason: string;
  keyFacts: string[];
  model: string;
  generatedAt: string;
  symbol?: string;
}

export interface InsightBaseRate {
  pattern: string;
  horizonWeeks: number;
  pctUp: number;
  medianFwd: number;
  n: number;
  headline: string;
}

export interface InsightComponent {
  label: string;
  met: boolean;
}

export interface TickerInsight {
  softBottoming: boolean;
  score: number;
  components: InsightComponent[];
  baseRate: InsightBaseRate | null;
}

export interface TickerDetailPayload {
  symbol: string;
  name: string;
  last: string;
  change: string;
  tone: Tone;
  series: { daily: Ohlcv[]; weekly: Ohlcv[]; monthly: Ohlcv[] };
  verdict: VerdictRow[];
  signals: SignalRow[];
  evidence: EvidenceItem[];
  events: ChartEvent[];
  kill: string;
  insight?: TickerInsight | null;
}
