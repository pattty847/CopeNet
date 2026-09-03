/** Catmull-Rom -> cubic bezier, so rotation tails read as smooth curves not jagged polylines. */
export function smoothPath(p: { x: number; y: number }[]): string {
  if (p.length < 2) return p.length ? `M${p[0].x.toFixed(1)},${p[0].y.toFixed(1)}` : '';
  let d = `M${p[0].x.toFixed(1)},${p[0].y.toFixed(1)}`;
  for (let i = 0; i < p.length - 1; i += 1) {
    const p0 = p[i - 1] || p[i];
    const p1 = p[i];
    const p2 = p[i + 1];
    const p3 = p[i + 2] || p2;
    const c1x = p1.x + (p2.x - p0.x) / 6;
    const c1y = p1.y + (p2.y - p0.y) / 6;
    const c2x = p2.x - (p3.x - p1.x) / 6;
    const c2y = p2.y - (p3.y - p1.y) / 6;
    d += `C${c1x.toFixed(1)},${c1y.toFixed(1)} ${c2x.toFixed(1)},${c2y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
  }
  return d;
}

// One distinct, legible-on-dark color per sector tail, assigned by symbol order so it stays stable across renders.
export const RRG_PALETTE = [
  '#6fb8f2',
  '#f2a65a',
  '#7fd88f',
  '#e07be0',
  '#f2d75a',
  '#f27b7b',
  '#7be0c9',
  '#b39ddb',
  '#f2955a',
  '#8fc9f2',
  '#c9e07b',
];

export function rrgColor(symbol: string, allSymbols: string[]): string {
  const idx = allSymbols.indexOf(symbol);
  return RRG_PALETTE[idx % RRG_PALETTE.length];
}

/** Label sizes are CSS pixels, independent of both chart zoom and SVG layout width. */
export function rrgLabelSize(active: boolean, zoom: number, pixelScale: number): number {
  return (active ? 10.5 : 9.5) / zoom / pixelScale;
}

export type RrgView = {
  scale: number;
  panX: number;
  panY: number;
};

export const W = 980;
export const H = 560;
export const L = 48;
export const R = 24;
export const T = 24;
export const B = 36;
export const MIN_SCALE = 1;
export const MAX_SCALE = 5;

export function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

export function axisTicks(domain: number): number[] {
  return [-domain, -domain / 2, 0, domain / 2, domain];
}

export function formatAxisValue(value: number): string {
  if (Math.abs(value) < 0.005) return '0';
  return Math.abs(value) >= 10 ? value.toFixed(0) : value.toFixed(1);
}

export function screenToPlotPoint(clientX: number, clientY: number, svg: SVGSVGElement, view: RrgView) {
  const rect = svg.getBoundingClientRect();
  const px = ((clientX - rect.left) / rect.width) * W;
  const py = ((clientY - rect.top) / rect.height) * H;
  return {
    x: L + (px - L) / view.scale - view.panX,
    y: T + (py - T) / view.scale - view.panY,
  };
}

export function constrainView(next: RrgView): RrgView {
  const plotW = W - L - R;
  const plotH = H - T - B;
  const extraX = plotW * (next.scale - 1) / next.scale;
  const extraY = plotH * (next.scale - 1) / next.scale;
  return {
    scale: next.scale,
    panX: clamp(next.panX, -extraX, 0),
    panY: clamp(next.panY, -extraY, 0),
  };
}
