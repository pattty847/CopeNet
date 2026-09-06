import type {
  IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, PrimitiveHoveredItem,
  SeriesAttachedParameter, UTCTimestamp,
} from 'lightweight-charts';
import type { ChartObject } from '../chartAgent/types';
import { hitDrawing, projectDrawing, type DrawingGeometry } from './geometry';
import type { ChartWorkspaceBridge } from './types';

export function paintDrawing(context: CanvasRenderingContext2D, geometry: DrawingGeometry, selected: boolean): void {
  const { object, points, width } = geometry;
  const [a, b] = points;
  context.strokeStyle = object.color;
  context.fillStyle = object.color;
  context.lineWidth = selected ? 2.5 : 1.5;
  context.setLineDash(object.owner.kind === 'agent' ? [6, 4] : []);
  context.beginPath();
  if (object.kind === 'level') {
    context.moveTo(0, a.y);
    context.lineTo(width, a.y);
  } else if (object.kind === 'trendline') {
    context.moveTo(a.x, a.y);
    context.lineTo(b.x, b.y);
  } else if (object.kind === 'zone') {
    const left = Math.min(a.x, b.x);
    const top = Math.min(a.y, b.y);
    const zoneWidth = Math.abs(b.x - a.x);
    const zoneHeight = Math.abs(b.y - a.y);
    context.globalAlpha = selected ? 0.2 : 0.1;
    context.fillRect(left, top, zoneWidth, zoneHeight);
    context.globalAlpha = 1;
    context.rect(left, top, zoneWidth, zoneHeight);
  } else {
    context.arc(a.x, a.y, 3, 0, 2 * Math.PI);
    context.fill();
  }
  context.stroke();
  context.setLineDash([]);
  if (object.label) {
    context.font = '11px "IBM Plex Mono", monospace';
    context.fillText(object.label, Math.max(5, Math.min(width - 50, a.x + 7)), a.y - 7, 260);
  }
  if (selected) {
    for (const point of points) {
      context.beginPath();
      context.arc(point.x, point.y, 4, 0, 2 * Math.PI);
      context.fillStyle = '#0b0b0d';
      context.fill();
      context.stroke();
    }
  }
}

/** Attached to the price series: LWC owns clipping, pane placement, log transforms and DPR. */
export class DrawingPrimitive implements ISeriesPrimitive {
  constructor(private readonly isVisible: () => boolean = () => true) {}
  private attachedState: SeriesAttachedParameter | null = null;
  private bridge: ChartWorkspaceBridge | undefined;
  private comparisonMode = false;
  private receiptKey = '';
  private preview: ChartObject | null = null;
  private geometry: DrawingGeometry[] = [];
  private readonly renderer: IPrimitivePaneRenderer = {
    draw: (target) => {
      const bridge = this.bridge;
      if (!bridge) return;
      const hidden = !bridge.enabled || this.comparisonMode;
      const eligible = hidden ? [] : bridge.objects.filter((object) => object.visible && object.timeframe === bridge.timeframe);
      try {
        this.updateAllViews();
        target.useMediaCoordinateSpace(({ context, mediaSize }) => {
          context.save();
          try {
            context.beginPath();
            context.rect(0, 0, mediaSize.width, mediaSize.height);
            context.clip();
            for (const geometry of this.geometry) paintDrawing(context, geometry, geometry.object.id === bridge.selectedObjectId);
          } finally { context.restore(); }
        });
        const objectIds = this.geometry.filter((geometry) => geometry.object.id !== '__preview').map((geometry) => geometry.object.id);
        const failed = eligible.some((object) => !objectIds.includes(object.id));
        const status = hidden || (bridge.objects.length > 0 && eligible.length === 0) ? 'hidden' : failed ? 'failed' : 'rendered';
        const reason = this.comparisonMode ? 'Drawings are hidden in comparison mode.' : !bridge.enabled ? 'Drawing layer is hidden.' :
          status === 'hidden' ? 'No visible drawings apply to this interval.' : failed ? 'Some drawing anchors are unavailable in the loaded candle range.' : undefined;
        const key = `${bridge.documentId}:${bridge.revision}:${status}:${objectIds.join(',')}`;
        if (key !== this.receiptKey && this.isVisible() && typeof document !== 'undefined' && document.visibilityState === 'visible') {
          this.receiptKey = key;
          // Do not update React state while LWC is inside its paint transaction.
          queueMicrotask(() => {
            if (this.bridge === bridge && this.attachedState) bridge.onRendered({ documentId: bridge.documentId, revision: bridge.revision, status, objectIds, reason });
          });
        }
      } catch (error) {
        const key = `${bridge.documentId}:${bridge.revision}:failed`;
        if (key !== this.receiptKey) {
          this.receiptKey = key;
          queueMicrotask(() => {
            if (this.bridge === bridge && this.attachedState) bridge.onRendered({ documentId: bridge.documentId, revision: bridge.revision, status: 'failed', objectIds: [], reason: String(error) });
          });
        }
      }
    },
  };
  private readonly views: IPrimitivePaneView[] = [{ zOrder: () => 'top', renderer: () => this.renderer }];

  attached(parameters: SeriesAttachedParameter): void { this.attachedState = parameters; }
  detached(): void { this.attachedState = null; this.geometry = []; }
  paneViews(): readonly IPrimitivePaneView[] { return this.views; }

  setState(bridge: ChartWorkspaceBridge | undefined, comparisonMode: boolean): void {
    this.bridge = bridge;
    this.comparisonMode = comparisonMode;
    // LWC skips primitives belonging to a hidden candle series in comparison mode.
    // A hidden receipt describes that state and must not wait for a paint that cannot run.
    if (bridge && (!bridge.enabled || comparisonMode)) {
      const key = `${bridge.documentId}:${bridge.revision}:hidden`;
      if (this.receiptKey !== key) {
        this.receiptKey = key;
        queueMicrotask(() => {
          if (this.bridge === bridge && this.attachedState) bridge.onRendered({
            documentId: bridge.documentId, revision: bridge.revision, status: 'hidden', objectIds: [],
            reason: comparisonMode ? 'Drawings are hidden in comparison mode.' : 'Drawing layer is hidden.',
          });
        });
      }
    }
    this.attachedState?.requestUpdate();
  }

  setPreview(object: ChartObject | null): void { this.preview = object; this.attachedState?.requestUpdate(); }

  updateAllViews(): void {
    const state = this.attachedState;
    const bridge = this.bridge;
    if (!state || !bridge || !bridge.enabled || this.comparisonMode) { this.geometry = []; return; }
    const size = state.chart.paneSize(0);
    const projection = {
      width: size.width, height: size.height,
      time: (timestamp: number) => state.chart.timeScale().timeToCoordinate(timestamp as UTCTimestamp),
      price: (value: number) => state.series.priceToCoordinate(value),
    };
    this.geometry = [...bridge.objects.filter((object) => object.visible && object.timeframe === bridge.timeframe), ...(this.preview ? [this.preview] : [])]
      .map((object) => projectDrawing(object, projection)).filter((item): item is DrawingGeometry => item !== null);
  }

  geometries(): DrawingGeometry[] { this.updateAllViews(); return this.geometry; }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    const geometry = [...this.geometries()].reverse().find((item) => item.object.id !== '__preview' && hitDrawing(item, { x, y }));
    return geometry ? { externalId: geometry.object.id, zOrder: 'top', cursorStyle: 'pointer' } : null;
  }
}
