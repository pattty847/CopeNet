import type {
  IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, PrimitiveHoveredItem,
  SeriesAttachedParameter, UTCTimestamp,
} from 'lightweight-charts';
import type { ChartObject } from '../chartAgent/types';
import type { Ohlcv } from '../types';
import { hitDrawing, projectDrawing, type DrawingGeometry, type Point } from './geometry';
import type { ChartWorkspaceBridge } from './types';
import { fillOpacityOf, shownOn, strokeOf } from './kinds';
import { lineDash } from '../chartStyle/types';
import { anchoredVwap, snapToBar } from './reads';

export function paintDrawing(context: CanvasRenderingContext2D, geometry: DrawingGeometry, selected: boolean): void {
  const { object, points, width } = geometry;
  const [a, b] = points;
  context.strokeStyle = object.color;
  context.fillStyle = object.color;
  const stroke = strokeOf(object);
  const fill = fillOpacityOf(object);
  context.lineWidth = stroke.width + (selected ? 1.5 : 0.5);
  context.setLineDash(lineDash(stroke.style));
  context.beginPath();
  if (geometry.regions) {
    for (const region of geometry.regions) {
      context.globalAlpha = Math.min(1, fill + (selected ? 0.1 : 0));
      context.fillStyle = region.color;
      context.fillRect(region.left, region.top, region.width, region.height);
      context.globalAlpha = 1;
      context.strokeStyle = region.color;
      context.strokeRect(region.left, region.top, region.width, region.height);
    }
  }
  if (geometry.path && geometry.path.length > 1) {
    context.moveTo(geometry.path[0].x, geometry.path[0].y);
    for (const point of geometry.path.slice(1)) context.lineTo(point.x, point.y);
    // A study's bands are drawn quieter than the study itself.
    context.stroke();
    context.globalAlpha = 0.55;
    for (const line of geometry.lines ?? []) {
      context.beginPath();
      context.moveTo(line.points[0].x, line.points[0].y);
      for (const point of line.points.slice(1)) context.lineTo(point.x, point.y);
      context.stroke();
    }
    context.globalAlpha = 1;
    context.beginPath();
  } else if (geometry.lines) {
    for (const line of geometry.lines) {
      context.beginPath();
      context.moveTo(line.points[0].x, line.points[0].y);
      for (const point of line.points.slice(1)) context.lineTo(point.x, point.y);
      context.stroke();
      if (line.label) {
        const point = line.points[line.points.length - 1];
        context.font = '10px "IBM Plex Mono", monospace';
        context.fillText(line.label, Math.max(5, Math.min(width - 90, point.x + 5)), point.y - 5);
      }
    }
  } else if (object.kind === 'level') {
    context.moveTo(0, a.y);
    context.lineTo(width, a.y);
  } else if (object.kind === 'zone') {
    const left = Math.min(a.x, b.x);
    const top = Math.min(a.y, b.y);
    const zoneWidth = Math.abs(b.x - a.x);
    const zoneHeight = Math.abs(b.y - a.y);
    context.globalAlpha = Math.min(1, fill + (selected ? 0.1 : 0));
    context.fillRect(left, top, zoneWidth, zoneHeight);
    context.globalAlpha = 1;
    context.rect(left, top, zoneWidth, zoneHeight);
  } else if (!geometry.regions) {
    context.arc(a.x, a.y, 3, 0, 2 * Math.PI);
    context.fill();
  }
  context.stroke();
  context.setLineDash([]);
  if (geometry.annotations) {
    context.font = '10px "IBM Plex Mono", monospace';
    for (const annotation of geometry.annotations) { context.fillStyle = annotation.color ?? object.color; context.fillText(annotation.text, Math.max(5, Math.min(width - 180, annotation.x)), Math.max(12, Math.min(geometry.height - 4, annotation.y))); }
    context.fillStyle = object.color;
  }
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

type SeriesProjection = { time: (timestamp: number) => number | null; price: (value: number) => number | null; width: number };

function seriesPath(values: Array<number | null>, bars: Ohlcv[], projection: SeriesProjection): Point[] {
  const path: Point[] = [];
  values.forEach((value, index) => {
    if (value == null) return;
    const x = projection.time(bars[index].t);
    const y = projection.price(value);
    if (x != null && y != null && Number.isFinite(y)) path.push({ x, y });
  });
  return path;
}

function anchoredVwapPath(object: ChartObject, bars: Ohlcv[], projection: SeriesProjection): Point[] {
  const path = seriesPath(anchoredVwap(object, bars).values, bars, projection);
  const last = path[path.length - 1];
  if (last && last.x < projection.width) path.push({ x: projection.width, y: last.y });
  return path;
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
      const eligible = hidden ? [] : bridge.objects.filter((object) => object.visible && shownOn(object, bridge.timeframe));
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
      time: (timestamp: number) => {
        const exact = state.chart.timeScale().timeToCoordinate(timestamp as UTCTimestamp);
        if (exact != null) return exact;
        const snapped = snapToBar(bridge.bars ?? [], timestamp);
        return snapped == null ? null : state.chart.timeScale().timeToCoordinate(snapped as UTCTimestamp);
      },
      price: (value: number) => state.series.priceToCoordinate(value),
      barsBetween: (from: number, to: number) => (bridge.bars ?? []).filter((bar) => bar.t > from && bar.t <= to).length,
    };
    const draft = bridge.draft;
    this.geometry = [...bridge.objects.map((object) => draft && draft.id === object.id ? draft : object).filter((object) => object.visible && shownOn(object, bridge.timeframe)), ...(this.preview ? [this.preview] : [])]
      .map((object) => {
        const geometry = projectDrawing(object, projection);
        if (geometry && object.kind === 'avwap') {
          geometry.path = anchoredVwapPath(object, bridge.bars ?? [], projection);
          geometry.lines = anchoredVwap(object, bridge.bars ?? []).bands.flatMap((band) => [band.upper, band.lower])
            .map((values) => ({ points: seriesPath(values, bridge.bars ?? [], projection) })).filter((line) => line.points.length > 1);
        }
        return geometry;
      }).filter((item): item is DrawingGeometry => item !== null);
  }

  geometries(): DrawingGeometry[] { this.updateAllViews(); return this.geometry; }

  hitTest(x: number, y: number): PrimitiveHoveredItem | null {
    const geometry = [...this.geometries()].reverse().find((item) => item.object.id !== '__preview' && hitDrawing(item, { x, y }));
    return geometry ? { externalId: geometry.object.id, zOrder: 'top', cursorStyle: 'pointer' } : null;
  }
}
