import type { ChartDetail, ChartEvidence, InstrumentRef } from '../chartAgent/types';
import type { ScanDefinition } from '../monitoring/types';

export interface ForecastSetup {
  kind: 'setup'; direction: 'long' | 'short'; thesis: string;
  entry: { kind: 'limit' | 'stop'; price: number }; stop: number;
  targets: { price: number; fraction: number }[];
  zones: { label: string; lower: number; upper: number }[];
  evidence: ChartEvidence[];
}
export type ForecastResult = ForecastSetup | { kind: 'no_setup'; thesis: string }
  | { kind: 'directional'; direction: 'bullish' | 'bearish' | 'neutral' | 'abstain'; thesis: string };
export interface ForecastMember {
  sessionKey: string; runId: string | null; observationId: string;
  attribution: { provider?: string; model?: string; requestedModel?: string; modelSource?: string; runStatus?: string;
    readCallCount?: number; reportedUsage?: Record<string, unknown> | null; usageStatus?: string; messageInputTokenEstimate?: number | null;
    [key: string]: unknown }; result?: ForecastResult;
  status: 'generating' | 'submitted' | 'failed'; errors: { recordedAt: string; reason: string }[];
}
export interface ForecastRecord {
  requestId: string; forecastId: string; documentId: string; observationId: string; sessionKey: string;
  instrument: InstrumentRef; provider: string; model: string; detail: ChartDetail; paired: boolean;
  entryExpirySessions: number; trackingScanId: string | null;
  status: 'requested' | 'generating' | 'published' | 'no_setup' | 'failed' | 'cancelled';
  failureReason?: string; finishedAt?: string; revision: number; requestedAt: string; capturedAt: number; publishedAt: string | null;
  referenceClose?: number; deadlineAt?: string | null; dueAt?: { fourWeek: string; eightWeek: string };
  tracking?: { status: 'scheduled' | 'paused' | 'unavailable' | 'host_disabled'; nextRunAt?: string | null; lastRunAt?: string | null };
  provenance?: Record<string, unknown>;
  members: { ta?: ForecastMember; directional?: ForecastMember };
  evaluation: ForecastEvaluation | null; events: Record<string, unknown>[];
  amendments: Record<string, unknown>[]; renderStatus: Omit<ForecastRenderReceipt, 'forecastId'>[];
}
export interface ForecastRequest {
  requestId: string; sessionKey: string; observationId: string; documentId: string;
  provider: string; model: string; detail: ChartDetail; paired: boolean; entryExpirySessions: number;
  trackingScanId?: string;
  tracking?: { scan: ScanDefinition; scopeToken: string };
}
export interface ForecastRenderReceipt {
  forecastId: string; revision: number; viewId: string;
  status: 'rendered' | 'hidden' | 'failed'; reason?: string;
}
export interface ForecastBridge {
  records: ForecastRecord[]; splitFingerprint?: string; hidden: ReadonlySet<string>; viewId: string;
  onSelect: (forecastId: string) => void;
  onRendered: (receipt: ForecastRenderReceipt) => void | Promise<void>;
}

export function forecastSetup(record: ForecastRecord): ForecastSetup | null {
  const result = record.members.ta?.result;
  return record.status === 'published' && result?.kind === 'setup' ? result : null;
}

export interface ForecastEvaluation {
  policyVersion?: string; state?: string; health?: string; reason?: string;
  entryPrice?: number | null; entryDate?: string | null; exitDate?: string | null;
  remainingFraction?: number; realizedPnl?: number; plannedRiskR?: number | null;
  holdingSessions?: number; activationDate?: string; evaluatedAt?: string;
  source?: { publicationBasisFactor?: number; splitFingerprint?: string; [key: string]: unknown };
  events?: { eventId: string; type: string; date: string; sessionClose: string; recordedAt: string; price?: number; fraction?: number; targetIndex?: number; reason?: string }[];
  horizons?: Record<string, { dueAt: string; endpointDate: string; endpointCloseAt: string; status: 'resolved' | 'pending'; referenceClose: number; endpointClose?: number; priceReturn?: number; members: Record<string, { direction: string; outcome: string }> }>;
}

export interface ForecastReport {
  cohorts?: { providers: string[]; models: string[] };
  policyVersion: string; attemptCount: number; setupCount: number;
  states: Record<string, number>; health: Record<string, number>;
  direction: Record<string, { counts: Record<string, number>; scoredCount: number; accuracy: number | null }>;
  paired: Record<string, { counts: Record<string, number>; pairedCount: number; correctnessDelta: number | null; distinctTickers: number; distinctPublicationDates: number }>;
  trade: { activatedCount: number; activationRate: number | null; scoredCount: number; meanPlannedRiskR: number | null; positiveCount: number; negativeCount: number; meanHoldingSessions: number | null };
  methodology: string;
}

export interface ForecastChart {
  publishedAt: number; deadlineAt: number;
  history: { t: number; close: number }[]; outcome: { t: number; close: number }[];
  health: string; reason: string | null; basis: 'publication'; historyAvailable: boolean;
}
