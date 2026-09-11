export type ScreenerConfig = {
  minCap: number;
  maxCap: number | null;
  minPrice: number;
  minDollarVolume: number;
};
export type Preset = {
  id: string;
  name: string;
  direction: string;
  metric: string;
  ascending: boolean;
  description: string;
  rules: string[];
  next: string;
};
export type Candidate = {
  id: string;
  symbol: string;
  exchange: string;
  name: string | null;
  sector: string | null;
  direction: string;
  price: number;
  change: number | null;
  marketCap: number;
  dollarVolume: number;
  averageVolume: number;
  relativeVolume: number | null;
  rsi: number | null;
  sma50: number | null;
  sma200: number | null;
  high52: number | null;
  monthReturn: number | null;
  bandWidth: number | null;
  distance50: number | null;
  distance200: number | null;
  drawdown: number | null;
  updateMode: string;
};
export type ScreenerRun = {
  id: string;
  version: number;
  startedAt: string;
  finishedAt: string;
  status: 'complete' | 'error';
  error: string | null;
  config: ScreenerConfig;
  presets: Preset[];
  source: string;
  received: number;
  truncated: boolean;
  eligible: number;
  excluded: Record<string, number>;
  screens: { id: string; rows: Candidate[]; missingFields: number }[];
};
export type ScreenerState = {
  presets: Preset[];
  config: ScreenerConfig;
  latest: ScreenerRun | null;
  running: boolean;
  history: Pick<ScreenerRun, 'id' | 'startedAt' | 'finishedAt' | 'status' | 'error'>[];
};
export type ScreenerPreview = {
  scopeToken: string;
  config: ScreenerConfig;
  scope: string;
  notes: string[];
  maxRows: number;
};
/** Cached daily bars for the setup visual; `bars` is null when the symbol is not cached. */
export type SetupBars = {
  symbol: string;
  bars: { t: number; o: number; h: number; l: number; c: number; v: number }[] | null;
  updatedAt: string | null;
};
