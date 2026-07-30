// Market Monitor — shared data contract.
// The backend emits matching JSON via the market.* RPCs; these types and
// core/market/models.py form the maintained wire contract.

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

// ---------- watchlist (user-curated, add/remove — distinct from the fixed UNIVERSE above) ----------
export interface WatchlistItem {
  symbol: string;
  name: string;
  value: string;
  change: string;
  tone: Tone;
  spark: number[];
}

export interface SymbolSearchResult {
  symbol: string;
  name: string;
  exchange: string;
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

export type YieldCurveRange = '1d' | '1w' | '1m';

export interface TreasuryYieldPoint {
  label: string;
  years: number;
  symbol: string;
  name: string;
  yield: number;
  changeBps: number;
}

export interface TreasuryYieldCurvePayload {
  status: 'live';
  source: 'us-treasury';
  sourceUrl: string;
  range: YieldCurveRange;
  asOf: string;
  comparisonAsOf: string;
  points: TreasuryYieldPoint[];
  spreads: { label: string; valueBps: number }[];
  shape: { label: string; detail: string };
  coverageNote: string;
}

export type RrgMode = 'fast' | 'default' | 'slow';

export interface RrgSector {
  symbol: string;
  name: string;
  tail: { x: number; y: number }[]; // x = RS-Ratio, y = RS-Momentum; last point = current; mirrors tails.default
  quadrant: 'leading' | 'weakening' | 'lagging' | 'improving';
  tails?: Partial<Record<RrgMode, { x: number; y: number }[]>>;
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
  type: 'Insider' | '8-K' | 'News' | 'Form 144';
  symbol: string;
  headline: string;
  source: string;
  tone: Tone;
  url?: string;
  t?: number; // unix seconds, for chart marker placement
  /** Badge-worthy anomaly: multi-insider buy window, or an 8-K in a high-signal category. */
  flag?: 'cluster' | 'high-signal';
  /** Transaction dollar value (Form 4 gross / 144 aggregate / cluster total). */
  value?: number | null;
  /** Per-share transaction price (Form 4 / implied for 144) — anchors chart cluster boxes. */
  price?: number | null;
  /** Share count for the transaction. */
  shares?: number | null;
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
  kind: 'insider' | '8-K' | 'planned-sale';
  glyph: string;
}

export interface InsiderNetWindow {
  days: number;
  buys: number;
  sells: number;
  /** Buys made with the insider's own cash (grants/vesting count as Form 4 "buys" but aren't).
   *  Absent on payloads cached before this field shipped. */
  openMarketBuys?: number;
  netShares: number;
  netValue?: number | null;
  tone: Tone;
}

export interface TickerEvidencePayload {
  symbol: string;
  evidence: EvidenceItem[];
  events: ChartEvent[];
  asOf: string;
  refreshed: boolean;
  /** Net Form 4 activity per trailing window (d30/d90); absent when no insider data. */
  insiderNet?: Record<string, InsiderNetWindow>;
  /** Typed upstream acquisition failures; empty filings do not produce warnings. */
  warnings?: string[];
}

// ---------- morning brief (overnight sentinel delta) ----------
export interface BriefSignalFlip {
  symbol: string;
  kind: string; // 'soft-bottoming' | 'trend'
  detail: string;
  tone: Tone;
}

export interface BriefRrgShift {
  symbol: string;
  name: string;
  fromQuadrant: string;
  toQuadrant: string;
  tone: Tone;
}

export interface BriefMover {
  symbol: string;
  name: string;
  last: string;
  changePct: number;
  tone: Tone;
}

/** What changed between the previous pre-market sweep and this one. Optional fields are
 *  omitted from the wire when null (backend drops None values). */
export interface MorningBriefPayload {
  briefDate: string; // YYYY-MM-DD, operator-local
  generatedAt: string;
  headline: string;
  newEvidence: EvidenceItem[];
  signalFlips: BriefSignalFlip[];
  rrgShifts: BriefRrgShift[];
  movers: BriefMover[];
  /** "today at the open" vs "last session" — set from the actual date of the newest daily bar. */
  moversLabel?: string;
  regimeShift?: { from: string; to: string };
  portfolioNote?: string;
  previousAsOf?: string;
  firstSweep: boolean;
  note?: string;
}

// ---------- economic calendar (Trading Economics, normalized by CopeNet) ----------
export interface EconomicCalendarEvent {
  id: string;
  date: string;
  country: string;
  event: string;
  category: string;
  importance: 1 | 2 | 3;
  actual?: string | null;
  forecast?: string | null;
  previous?: string | null;
  revised?: string | null;
  unit?: string | null;
  reference?: string | null;
  source?: string | null;
  sourceUrl?: string | null;
}

export interface EconomicCalendarPayload {
  configured: boolean;
  provider: string;
  sourceUrl: string;
  retrievedAt?: string;
  windowStart: string;
  windowEnd: string;
  stale: boolean;
  error?: string;
  events: EconomicCalendarEvent[];
}

// ---------- fundamentals (SEC XBRL, for the chart overlay) ----------
/** One quarterly XBRL data point. Keys mirror CopeTech-Edgar's trend entries verbatim
 *  (snake_case pcts — this payload passes through the RPC unreshaped for now). */
export interface FundamentalsQuarter {
  period: string; // "Q1 2026"
  date: string; // period end, YYYY-MM-DD
  value: number;
  yoy_pct?: number | null;
  qoq_pct?: number | null;
}

export interface TickerFundamentals {
  entityName?: string;
  revenueQuarterly: FundamentalsQuarter[];
  epsQuarterly: FundamentalsQuarter[];
  /** Foreign 20-F filers report annual-only XBRL — the overlay falls back to these. */
  revenueAnnual?: FundamentalsQuarter[];
  epsAnnual?: FundamentalsQuarter[];
}

// ---------- canonical financial series ----------
export type FinancialFrequency = 'quarterly' | 'annual' | 'ttm';

export interface FinancialSeriesSource {
  taxonomy: string;
  concept: string;
  form: string;
  filed: string;
  accessionNumber: string;
  frame?: string | null;
  sourceUrl?: string | null;
}

export interface FinancialSeriesObservation {
  periodStart: string;
  periodEnd: string;
  availableAt: string;
  alignedAt: string;
  value: number;
  unit: string;
  frequency: FinancialFrequency;
  fiscalYear?: number | null;
  fiscalPeriod?: string | null;
  reported: boolean;
  derived: boolean;
  derivation?: string | null;
  confidence: number;
  qualityFlags: string[];
  sources: FinancialSeriesSource[];
}

export interface FinancialSeriesPayload {
  symbol: string;
  cik?: number | string | null;
  entityName?: string | null;
  metric: string;
  label: string;
  frequency: FinancialFrequency;
  basis: 'reported' | 'canonical';
  alignment: 'period_end' | 'availability';
  asOf?: string | null;
  normalizationVersion: number;
  retrievedAt?: string | null;
  rawFactCount: number;
  observations: FinancialSeriesObservation[];
  warnings: string[];
}

export interface ValuationSeriesObservation {
  timestamp: string;
  alignedAt: string;
  value: number | null;
  unit: 'ratio';
  price: number;
  priceBasis: 'split_adjusted';
  priceSource?: {
    provider: string;
    timestamp: string;
    basis: 'split_adjusted';
  };
  epsTtm: number | null;
  epsTtmAdjusted: number | null;
  epsSplitAdjustmentFactor: number | null;
  epsAvailableAt: string | null;
  epsPeriodEnd: string | null;
  qualityFlags: string[];
  sources: FinancialSeriesSource[];
}

export interface ValuationSeriesPayload {
  symbol: string;
  metric: 'trailing_pe';
  label: 'Trailing P/E';
  frequency: 'price';
  alignment: 'price_timestamp';
  priceBasis: 'split_adjusted';
  epsMetric: 'diluted_eps';
  epsFrequency: 'ttm';
  normalizationVersion: number;
  retrievedAt?: string | null;
  rawFactCount: number;
  observations: ValuationSeriesObservation[];
  warnings: string[];
}

export type OverlaySeriesPayload = FinancialSeriesPayload | ValuationSeriesPayload;

// ---------- forward ledger (model calls scored at horizon) ----------
/** Claim rows come from the backend's dataclass dump — snake_case keys, unlike the rest
 *  of the market wire. Lived-with for phase 1. */
export interface LedgerHorizonSlot {
  due_at: string;
  resolved_at?: string | null;
  return_pct?: number | null;
  excess_pct?: number | null;
  outcome?: 'correct' | 'incorrect' | 'push' | 'unscoreable' | null;
}

export interface LedgerClaim {
  claim_id: string;
  created_at: string;
  kind: 'regime' | 'lean' | 'attention';
  target: string;
  value: string;
  confidence?: string | null;
  model: string;
  note: string;
  horizons: Record<string, LedgerHorizonSlot>;
}

export interface LedgerKindStats {
  correct: number;
  incorrect: number;
  push: number;
  accuracyPct: number | null;
}

export interface LedgerReport {
  rulesVersion: string;
  totalClaims: number;
  pendingHorizons: number;
  stats: Record<'regime' | 'lean' | 'attention', Record<string, LedgerKindStats>>;
  recent: LedgerClaim[];
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
  lean?: 'bullish' | 'bearish' | 'neutral';
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
  /** Headline stats from yfinance; keys absent when unresolvable (indexes, some ETFs). */
  stats?: { marketCap?: number; yearHigh?: number; yearLow?: number; avgVolume3m?: number } | null;
}
