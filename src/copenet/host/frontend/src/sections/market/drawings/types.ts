import type { ForecastBridge } from '../forecasts/types';
import type { ChartObject, ChartSelection, ChartViewport, DrawingPatch } from '../chartAgent/types';
import type { Ohlcv } from '../types';

export type DrawingMode = 'select' | 'range' | ChartObject['kind'];
export interface DrawingProposal {
  kind: ChartObject['kind'];
  anchors: ChartObject['anchors'];
  timeframe: ChartObject['timeframe'];
}
export interface ChartRenderReceipt {
  documentId: string;
  revision: number;
  status: 'rendered' | 'hidden' | 'failed';
  objectIds: string[];
  reason?: string;
}
export interface ChartWorkspaceBridge {
  forecasts?: ForecastBridge;
  documentId: string;
  revision: number;
  objects: ChartObject[];
  timeframe: ChartObject['timeframe'];
  /** Real candles for derived drawings such as anchored VWAP. */
  bars?: Ohlcv[];
  enabled: boolean;
  /** Pause edits during a save while continuing to show the committed document. */
  interactionEnabled?: boolean;
  selectedObjectId: string | null;
  mode: DrawingMode;
  selection?: ChartSelection | null;
  onViewport: (viewport: ChartViewport) => void;
  onSelectRange: (range: ChartSelection | null) => void;
  onSelectObject: (id: string | null) => void;
  onDeleteObject: (id: string) => void;
  onOpenDrawingSettings?: (id: string) => void;
  onCancelDrawing?: () => void;
  onCreate: (proposal: DrawingProposal) => void;
  onUpdate: (proposal: { id: string; patch: DrawingPatch }) => void;
  /** Set for a few seconds after a delete, so one tap on a phone is never final. */
  /** A just-placed text drawing: the settings bar opens its label field so typing is next. */
  labelRequestId?: string | null;
  deleted?: { label: string } | null;
  onUndoDelete?: () => void;
  onRendered: (receipt: ChartRenderReceipt) => void;
}
