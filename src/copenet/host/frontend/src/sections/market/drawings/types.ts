import type { ChartObject, ChartSelection, ChartViewport } from '../chartAgent/types';

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
  documentId: string;
  revision: number;
  objects: ChartObject[];
  timeframe: ChartObject['timeframe'];
  enabled: boolean;
  /** Pause edits during a save while continuing to show the committed document. */
  interactionEnabled?: boolean;
  selectedObjectId: string | null;
  mode: DrawingMode;
  selection?: ChartSelection | null;
  onViewport: (viewport: ChartViewport) => void;
  onSelectRange: (range: ChartSelection | null) => void;
  onSelectObject: (id: string | null) => void;
  onCreate: (proposal: DrawingProposal) => void;
  onUpdate: (proposal: { id: string; anchors: ChartObject['anchors'] }) => void;
  onRendered: (receipt: ChartRenderReceipt) => void;
}
