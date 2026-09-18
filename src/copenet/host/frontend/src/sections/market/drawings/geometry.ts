import type { ChartAnchor, ChartObject } from '../chartAgent/types';
import { DOWN_COLOR, DRAWING_KINDS, UP_COLOR } from './kinds';
import { fibLevelValues } from './reads';

export interface Point { x: number; y: number }
export interface DrawingGeometry {
  object: ChartObject;
  points: Point[];
  width: number;
  height: number;
  lines?: Array<{ points: Point[]; label?: string }>;
  regions?: Array<{ left: number; top: number; width: number; height: number; color: string; label?: string }>;
  path?: Point[];
  annotations?: Array<{ x: number; y: number; text: string; color?: string }>;
}
export interface CoordinateProjection {
  time: (timestamp: number) => number | null;
  /** Candles between two timestamps; absent in contexts that have no bar list. */
  barsBetween?: (from: number, to: number) => number;
  price: (value: number) => number | null;
  width: number;
  height: number;
}


function lineToBoundary(start: Point, end: Point, width: number, height: number, both = false): Point[] {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  if (dx === 0 && dy === 0) return [start, end];
  const candidates: Array<{ scale: number; point: Point }> = [];
  if (dx !== 0) for (const x of [0, width]) { const scale = (x - start.x) / dx; if (scale > 0) candidates.push({ scale, point: { x, y: start.y + scale * dy } }); }
  if (dy !== 0) for (const y of [0, height]) { const scale = (y - start.y) / dy; if (scale > 0) candidates.push({ scale, point: { x: start.x + scale * dx, y } }); }
  const forward = candidates.filter(({ point }) => point.x >= -0.1 && point.x <= width + 0.1 && point.y >= -0.1 && point.y <= height + 0.1)
    .sort((a, z) => a.scale - z.scale)[0]?.point ?? end;
  if (!both) return [start, forward];
  const reverse = lineToBoundary(start, { x: start.x - dx, y: start.y - dy }, width, height, false)[1];
  return [reverse, forward];
}

function addFibLines(points: Point[], object: ChartObject, projection: CoordinateProjection): Array<{ points: Point[]; label?: string }> {
  const [a, b] = object.anchors;
  return fibLevelValues(a.value, b.value).map(({ ratio, value }) => {
    const y = projection.price(value);
    return y == null ? null : { points: [{ x: Math.min(points[0].x, points[1].x), y }, { x: Math.max(points[0].x, points[1].x), y }], label: `${(ratio * 100).toFixed(1)}%` };
  }).filter((line): line is { points: Point[]; label: string } => line !== null);
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
  if (points.length !== DRAWING_KINDS[object.kind].anchors) return null;
  const geometry: DrawingGeometry = { object, points, width: projection.width, height: projection.height };
  if (object.kind === 'horizontal_ray') geometry.lines = [{ points: [points[0], { x: projection.width, y: points[0].y }] }];
  if (object.kind === 'vertical_line') geometry.lines = [{ points: [{ x: points[0].x, y: 0 }, { x: points[0].x, y: projection.height }] }];
  if (object.kind === 'ray') geometry.lines = [{ points: lineToBoundary(points[0], points[1], projection.width, projection.height) }];
  if (object.kind === 'trendline') geometry.lines = [{ points }];
  if (object.kind === 'extended_trendline') geometry.lines = [{ points: lineToBoundary(points[0], points[1], projection.width, projection.height, true) }];
  if (object.kind === 'fib_retracement') geometry.lines = addFibLines(points, object, projection);
  if (object.kind === 'measurement') {
    const [a, b] = object.anchors;
    const change = b.value - a.value;
    const percent = a.value === 0 ? 0 : (change / a.value) * 100;
    const days = Math.abs(b.t - a.t) / 86400;
    const bars = projection.barsBetween?.(Math.min(a.t, b.t), Math.max(a.t, b.t));
    const color = change >= 0 ? UP_COLOR : DOWN_COLOR;
    const left = Math.min(points[0].x, points[1].x);
    const top = Math.min(points[0].y, points[1].y);
    // A signed box, not a ray with a caption: green gained, red lost, read before any number.
    geometry.regions = [{ left, top, width: Math.abs(points[1].x - points[0].x), height: Math.abs(points[1].y - points[0].y), color }];
    geometry.annotations = [{ x: left + 6, y: top + 14, color,
      text: `${change >= 0 ? '+' : ''}${change.toFixed(2)} (${percent >= 0 ? '+' : ''}${percent.toFixed(1)}%) · ${bars != null ? `${bars} bars · ` : ''}${days.toFixed(0)}d` }];
  }
  if (object.kind === 'channel') {
    const [a, b, offset] = points;
    geometry.lines = [{ points: lineToBoundary(a, b, projection.width, projection.height, true), label: 'basis' },
      { points: lineToBoundary(offset, { x: offset.x + b.x - a.x, y: offset.y + b.y - a.y }, projection.width, projection.height, true), label: 'parallel' }];
  }
  if (object.kind === 'position') {
    const [entry, target, stop] = points;
    const left = Math.min(entry.x, target.x, stop.x);
    const right = Math.max(entry.x, target.x, stop.x);
    const profitTop = Math.min(entry.y, target.y);
    const riskTop = Math.min(entry.y, stop.y);
    geometry.regions = [
      { left, top: profitTop, width: right - left, height: Math.abs(entry.y - target.y), color: UP_COLOR, label: 'target' },
      { left, top: riskTop, width: right - left, height: Math.abs(entry.y - stop.y), color: DOWN_COLOR, label: 'stop' },
    ];
    geometry.annotations = [
      { x: entry.x + 6, y: entry.y - 6, text: `Entry ${object.anchors[0].value.toFixed(2)}` },
      { x: target.x + 6, y: target.y - 6, text: `Target ${object.anchors[1].value.toFixed(2)}` },
      { x: stop.x + 6, y: stop.y + 14, text: `Stop ${object.anchors[2].value.toFixed(2)}` },
    ];
  }
  return geometry;
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
  if (geometry.path?.some((current, index) => index > 0 && segmentDistance(point, geometry.path![index - 1], current) <= tolerance)) return true;
  if (geometry.lines?.some((line) => line.points.some((current, index) => index > 0 && segmentDistance(point, line.points[index - 1], current) <= tolerance))) return true;
  if (geometry.regions?.some((region) => point.x >= region.left - tolerance && point.x <= region.left + region.width + tolerance && point.y >= region.top - tolerance && point.y <= region.top + region.height + tolerance)) return true;
  switch (geometry.object.kind) {
    case 'level': return Math.abs(point.y - a.y) <= tolerance;
    case 'label': return Math.hypot(point.x - a.x, point.y - a.y) <= tolerance ||
      (point.x >= a.x + 6 && point.x <= a.x + 6 + Math.min(260, geometry.object.label.length * 7) && point.y >= a.y - 19 && point.y <= a.y);
    case 'zone': return point.x >= Math.min(a.x, b.x) - tolerance && point.x <= Math.max(a.x, b.x) + tolerance &&
      point.y >= Math.min(a.y, b.y) - tolerance && point.y <= Math.max(a.y, b.y) + tolerance;
    case 'trendline': return segmentDistance(point, a, b) <= tolerance;
    case 'horizontal_ray': return Math.abs(point.y - a.y) <= tolerance && point.x >= a.x - tolerance;
    case 'vertical_line': return Math.abs(point.x - a.x) <= tolerance;
    case 'callout': return Math.hypot(point.x - a.x, point.y - a.y) <= tolerance ||
      (point.x >= a.x + 6 && point.x <= a.x + 6 + Math.min(260, geometry.object.label.length * 7) && point.y >= a.y - 24 && point.y <= a.y + 5);
    default: return false;
  }
}

/** A fingertip is far wider than a mouse pointer; touch gets a matching hit area. */
export const TOUCH_HIT_TOLERANCE = 18;

export function anchorIndexAt(geometry: DrawingGeometry, point: Point, tolerance = 10): number {
  return geometry.points.findIndex((anchor) => Math.hypot(point.x - anchor.x, point.y - anchor.y) <= tolerance);
}

export function replaceAnchor(anchors: ChartAnchor[], index: number, anchor: ChartAnchor): ChartAnchor[] {
  return anchors.map((current, i) => i === index ? anchor : current);
}
