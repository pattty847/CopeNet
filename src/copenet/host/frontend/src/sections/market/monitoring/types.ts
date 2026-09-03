export interface ScanDefinition {
  id: string;
  revision: number;
  name: string;
  enabled: boolean;
  includeUniverse: boolean;
  symbols: string[];
  watchlists: string[];
  excludeSymbols: string[];
  sources: string[];
  times: string[];
  days: number[];
  timezone: string;
  publishBrief: boolean;
  interpret: boolean;
}

export interface ScanRun {
  id: string;
  scanId: string;
  name?: string;
  status: string;
  startedAt: string;
  finishedAt?: string;
  errors?: { source: string; symbol: string; message: string }[];
  resolvedSymbols?: string[];
  sources?: string[];
  cacheHits?: number;
  fetched?: number;
  results?: { source: string; symbol: string; updatedAt: string; cached: boolean; payload?: unknown; bars?: number }[];
  screens?: { symbol: string; signals: Record<string, unknown> }[];
}

export interface Scan extends ScanDefinition {
  resolvedSymbols: string[];
  contextSymbols: string[];
  nextRunAt: string | null;
  issues: string[];
  lastRun: ScanRun | null;
}

export interface ScansState {
  scans: Scan[];
  runs: ScanRun[];
  watchlists: { name: string; symbols: string[] }[];
  sources: { id: string; label: string; scope: string }[];
  nextRunAt: string | null;
  nextScanId: string | null;
  schedulerEnabled: boolean;
}

export interface ScanPreview {
  scopeToken: string;
  nextRunAt?: string | null;
  notes?: string[];
  resolvedSymbols: string[];
  contextSymbols: string[];
  inclusions: { symbol: string; reasons: string[] }[];
  issues: string[];
  cacheHits: number;
  fetchSymbols: string[];
  work: { source: string; symbol: string; status: string }[];
}

export interface AlertOperand {
  kind: 'price' | 'indicator' | 'constant';
  indicatorId?: string;
  config?: Record<string, number | string | boolean>;
  output?: string;
  value?: number;
}

export interface AlertRule {
  alertId: string;
  revision: number;
  symbol: string;
  timeframe: 'daily' | 'weekly' | 'monthly';
  scanId: string;
  enabled: boolean;
  oneShot: boolean;
  direction: 'above' | 'below';
  left: AlertOperand;
  right: AlertOperand;
  destinationIds: string[];
  telegramAuthorized: boolean;
  status: string;
  createdAt?: string;
  updatedAt?: string;
  lastEvaluatedAt?: string | null;
  lastCandleAt?: string | null;
  observation?: { t: number; left: number; right: number; candleCloseAt: string; priceBasis: string } | null;
  error?: string | null;
}

export interface AlertEvent {
  eventId: string;
  alertId: string;
  symbol: string;
  timeframe: string;
  condition: string;
  leftValue: number;
  rightValue: number;
  candleCloseAt: string;
  evaluatedAt: string;
  scanId: string;
}

export interface IndicatorOption {
  id: string;
  name: string;
  inputs: import('../indicators/types').IndicatorInput[];
  outputs: { key: string; label: string }[];
  defaults: Record<string, number | string | boolean>;
  warmup: number;
}

export interface AlertsState {
  alerts: AlertRule[];
  events: AlertEvent[];
}
export interface Delivery {
  id: string;
  alertId?: string;
  destinationId: string;
  status: string;
  createdAt: string;
  error?: string | null;
  attempts?: { startedAt: string; status: string; error?: string }[];
}
export interface NotificationsState {
  transportConfigured: boolean;
  destinations: { id: string; displayName: string; status: string; requiresApproval: boolean }[];
  deliveries: Delivery[];
}
