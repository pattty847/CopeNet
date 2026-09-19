import type { ChartTimeframe } from '../chartRanges';
import type { Ohlcv } from '../types';

export interface InstrumentRef {
  instrumentId: string;
  symbol: string;
  assetClass: string;
  source: string;
  currency: string | null;
}

export interface ChartAnchor { t: number; value: number; evidenceField?: 'o' | 'h' | 'l' | 'c'; verified?: 'exact' | 'in-range' | 'out-of-range' | 'unchecked' }
export interface ChartEvidence { observationId: string; resourceKey: string; from?: number; to?: number }
export type DrawingKind = 'level' | 'zone' | 'trendline' | 'extended_trendline' | 'label' | 'horizontal_ray' | 'ray' | 'vertical_line' |
  'measurement' | 'position' | 'channel' | 'avwap' | 'fib_retracement' | 'callout';
export interface ChartObject {
  id: string;
  kind: DrawingKind;
  anchors: ChartAnchor[];
  timeframe: ChartTimeframe;
  label: string;
  color: string;
  visible: boolean;
  lineWidth?: number;
  lineStyle?: 'solid' | 'dashed' | 'dotted';
  fillOpacity?: number;
  locked?: boolean;
  /** Where it is shown. Absent means its own `timeframe` only. */
  timeframes?: ChartTimeframe[];
  showStats?: boolean;
  params?: Record<string, number | string | boolean>;
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
  kind: 'candles' | 'indicator' | 'financial' | 'comparison' | 'evidence' | 'panel' | 'quote' | 'drawings' | 'drawing_reads';
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
export type ChartDetail = 'quick' | 'balanced' | 'deep' | 'exhaustive';
export interface MarketContext {
  observationId: string;
  documentId: string;
  viewId: string;
  detail: ChartDetail;
  access: 'read' | 'annotate';
}
export type DrawingPatch = Partial<Pick<ChartObject, 'anchors' | 'label' | 'color' | 'visible' | 'rationale' | 'evidence' | 'lineWidth' | 'lineStyle' | 'fillOpacity' | 'locked' | 'kind' | 'timeframes' | 'showStats' | 'params'>>;
export type ChartOperation =
  | { kind: 'create'; object: Omit<ChartObject, 'owner'> }
  | { kind: 'update'; objectId: string; patch: DrawingPatch }
  | { kind: 'delete'; objectId: string };
export interface DrawingReceipt {
  batchId: string;
  documentId: string;
  revision: number;
  status: string;
  document?: ChartDocument;
  renderStatus?: string;
}
