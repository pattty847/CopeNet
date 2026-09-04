import type { ChartTimeframe } from '../chartRanges';

export interface InstrumentRef {
  instrumentId: string;
  symbol: string;
  assetClass: string;
  source: string;
  currency: string | null;
}

export interface ChartAnchor { t: number; value: number }
export interface ChartEvidence { observationId: string; resourceKey: string; from?: number; to?: number }
export type DrawingKind = 'level' | 'zone' | 'trendline' | 'label';
export interface ChartObject {
  id: string;
  kind: DrawingKind;
  anchors: ChartAnchor[];
  timeframe: ChartTimeframe;
  label: string;
  color: string;
  visible: boolean;
  rationale: string;
  evidence: ChartEvidence[];
  owner: { kind: 'agent' | 'operator'; sessionKey?: string; runId?: string };
}

export interface ChartDocument {
  documentId: string;
  workspaceId: string;
  instrument: InstrumentRef;
  revision: number;
  objects: ChartObject[];
}

export interface ChartViewport {
  from: number | null;
  to: number | null;
  logicalFrom: number | null;
  logicalTo: number | null;
}
export interface ChartSelection { from: number; to: number }
export interface ViewResource {
  key: string;
  kind: 'candles' | 'indicator' | 'financial' | 'comparison' | 'evidence' | 'panel' | 'quote' | 'drawings';
  label: string;
  unit?: string;
  status: 'loaded' | 'empty' | 'stale' | 'error' | 'not-loaded';
  observedAt?: string | null;
  rows: Record<string, unknown>[];
  metadata: Record<string, unknown>;
}
export interface MarketCapture {
  schemaVersion: 1;
  viewId: string;
  viewRevision: number;
  instrument: InstrumentRef;
  timeframe: ChartTimeframe;
  range: string;
  viewport: ChartViewport;
  selection: ChartSelection | null;
  settings: Record<string, unknown>;
  resources: ViewResource[];
  documentId: string;
  documentRevision: number;
}
export type ChartDetail = 'quick' | 'balanced' | 'deep';
export interface MarketContext {
  observationId: string;
  documentId: string;
  viewId: string;
  detail: ChartDetail;
  access: 'read' | 'annotate';
}
export type ChartOperation =
  | { kind: 'create'; object: Omit<ChartObject, 'owner'> }
  | { kind: 'update'; objectId: string; patch: Partial<Pick<ChartObject, 'anchors' | 'label' | 'color' | 'visible' | 'rationale' | 'evidence'>> }
  | { kind: 'delete'; objectId: string };
export interface DrawingReceipt {
  batchId: string;
  documentId: string;
  revision: number;
  status: string;
  document?: ChartDocument;
  renderStatus?: string;
}
