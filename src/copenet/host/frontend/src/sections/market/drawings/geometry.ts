import type { ChartAnchor, ChartObject } from '../chartAgent/types';

export interface Point { x: number; y: number }
export interface DrawingGeometry {
  object: ChartObject;
  points: Point[];
  width: number;
  height: number;
}
export interface CoordinateProjection {
  time: (timestamp: number) => number | null;
  price: (value: number) => number | null;
  width: number;
  height: number;
}

/** Never interpolate time by elapsed seconds: the chart axis is indexed by candles. */
export function projectDrawing(object: ChartObject, projection: CoordinateProjection): DrawingGeometry | null {
  const points: Point[] = [];
  for (const anchor of object.anchors) {
    const x = projection.time(anchor.t);
    const y = projection.price(anchor.value);
    if (x == null || y == null || !Number.isFinite(x) || !Number.isFinite(y)) return null;
    points.push({ x, y });
  }
  if (points.length !== (object.kind === 'zone' || object.kind === 'trendline' ? 2 : 1)) return null;
  return { object, points, width: projection.width, height: projection.height };
}

export function segmentDistance(point: Point, start: Point, end: Point): number {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = dx * dx + dy * dy;
  const position = length === 0 ? 0 : Math.max(0, Math.min(1, ((point.x - start.x) * dx + (point.y - start.y) * dy) / length));
  return Math.hypot(point.x - start.x - position * dx, point.y - start.y - position * dy);
}

export function hitDrawing(geometry: DrawingGeometry, point: Point, tolerance = 7): boolean {
  if (point.x < 0 || point.x > geometry.width || point.y < 0 || point.y > geometry.height) return false;
  const [a, b] = geometry.points;
  switch (geometry.object.kind) {
    case 'level': return Math.abs(point.y - a.y) <= tolerance;
    case 'label': return Math.hypot(point.x - a.x, point.y - a.y) <= tolerance ||
      (point.x >= a.x + 6 && point.x <= a.x + 6 + Math.min(260, geometry.object.label.length * 7) && point.y >= a.y - 19 && point.y <= a.y);
    case 'trendline': return segmentDistance(point, a, b) <= tolerance;
    case 'zone': return point.x >= Math.min(a.x, b.x) - tolerance && point.x <= Math.max(a.x, b.x) + tolerance &&
      point.y >= Math.min(a.y, b.y) - tolerance && point.y <= Math.max(a.y, b.y) + tolerance;
  }
}

export function anchorIndexAt(geometry: DrawingGeometry, point: Point): number {
  return geometry.points.findIndex((anchor) => Math.hypot(point.x - anchor.x, point.y - anchor.y) <= 10);
}

export function replaceAnchor(anchors: ChartAnchor[], index: number, anchor: ChartAnchor): ChartAnchor[] {
  return anchors.map((current, i) => i === index ? anchor : current);
}
