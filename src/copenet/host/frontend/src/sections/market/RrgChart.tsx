import { useEffect, useId, useMemo, useRef, useState } from 'react';
import type { Panel, RrgMode, RrgSector } from './types';
import { MM, PanelCard, mono } from './marketUi';

const RRG_MODES: { mode: RrgMode; label: string; title: string }[] = [
  { mode: 'fast', label: 'FAST', title: 'Fast · 8w level · 2w momentum · EMA 2' },
  { mode: 'default', label: 'STD', title: 'Standard · 13w level · 4w momentum · EMA 3' },
  { mode: 'slow', label: 'SLOW', title: 'Slow · 26w level · 8w momentum · EMA 5' },
];

/** Catmull-Rom -> cubic bezier, so rotation tails read as smooth curves not jagged polylines. */
function smoothPath(p: { x: number; y: number }[]): string {
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
const RRG_PALETTE = [
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

function rrgColor(symbol: string, allSymbols: string[]): string {
  const idx = allSymbols.indexOf(symbol);
  return RRG_PALETTE[idx % RRG_PALETTE.length];
}

type RrgView = {
  scale: number;
  panX: number;
  panY: number;
};

const W = 980;
const H = 560;
const L = 48;
const R = 24;
const T = 24;
const B = 36;
const MIN_SCALE = 1;
const MAX_SCALE = 5;

function clamp(v: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, v));
}

function axisTicks(domain: number): number[] {
  return [-domain, -domain / 2, 0, domain / 2, domain];
}

function formatAxisValue(value: number): string {
  if (Math.abs(value) < 0.005) return '0';
  return Math.abs(value) >= 10 ? value.toFixed(0) : value.toFixed(1);
}

function screenToPlotPoint(clientX: number, clientY: number, svg: SVGSVGElement, view: RrgView) {
  const rect = svg.getBoundingClientRect();
  const px = ((clientX - rect.left) / rect.width) * W;
  const py = ((clientY - rect.top) / rect.height) * H;
  return {
    x: L + (px - L) / view.scale - view.panX,
    y: T + (py - T) / view.scale - view.panY,
  };
}

function constrainView(next: RrgView): RrgView {
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

export function Rrg({ panel, onOpen, note }: { panel: Panel<RrgSector[]>; onOpen: (s: string) => void; note?: string }) {
  const clipId = useId();
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragRef = useRef<{ pointerId: number; x: number; y: number; panX: number; panY: number; moved: boolean } | null>(null);
  const suppressClickRef = useRef(false);
  const [view, setView] = useState<RrgView>({ scale: 1, panX: 0, panY: 0 });
  const [hoveredSymbol, setHoveredSymbol] = useState<string | null>(null);
  const [pinnedSymbol, setPinnedSymbol] = useState<string | null>(null);
  const [mode, setMode] = useState<RrgMode>('default');

  const sectors = useMemo(
    () => panel.data.map((s) => ({ ...s, pts: s.tails?.[mode] ?? s.tail })),
    [panel.data, mode],
  );
  const allSymbols = useMemo(() => sectors.map((s) => s.symbol), [sectors]);
  const activeSymbol = pinnedSymbol || hoveredSymbol;
  const renderedSectors = useMemo(() => {
    if (!activeSymbol) return sectors;
    return [...sectors].sort((a, b) => Number(a.symbol === activeSymbol) - Number(b.symbol === activeSymbol));
  }, [activeSymbol, sectors]);

  const xs = sectors.flatMap((s) => s.pts.map((p) => Math.abs(p.x)));
  const ys = sectors.flatMap((s) => s.pts.map((p) => Math.abs(p.y)));
  const domX = Math.max(1, ...xs) * 1.12;
  const domY = Math.max(1, ...ys) * 1.12;
  const clampDomain = (v: number, d: number) => Math.max(-d, Math.min(d, v));
  const sx = (x: number) => L + ((clampDomain(x, domX) + domX) / (2 * domX)) * (W - L - R);
  const sy = (y: number) => T + ((domY - clampDomain(y, domY)) / (2 * domY)) * (H - T - B);
  const cx = sx(0);
  const cy = sy(0);
  const isZoomed = view.scale > 1.01;
  const plotTransform = `translate(${L} ${T}) scale(${view.scale}) translate(${view.panX} ${view.panY}) translate(${-L} ${-T})`;
  const plotW = W - L - R;
  const plotH = H - T - B;
  const visibleSXMin = L - view.panX;
  const visibleSXMax = L + plotW / view.scale - view.panX;
  const visibleSYMin = T - view.panY;
  const visibleSYMax = T + plotH / view.scale - view.panY;
  const visibleXMin = ((visibleSXMin - L) / plotW) * 2 * domX - domX;
  const visibleXMax = ((visibleSXMax - L) / plotW) * 2 * domX - domX;
  const visibleYMax = domY - ((visibleSYMin - T) / plotH) * 2 * domY;
  const visibleYMin = domY - ((visibleSYMax - T) / plotH) * 2 * domY;

  const setZoom = (nextScale: number, anchor?: { x: number; y: number }) => {
    setView((current) => {
      const scale = clamp(nextScale, MIN_SCALE, MAX_SCALE);
      const target = anchor || { x: L + (W - L - R) / 2, y: T + (H - T - B) / 2 };
      const ratio = current.scale / scale;
      return constrainView({
        scale,
        panX: L + (target.x + current.panX - L) * ratio - target.x,
        panY: T + (target.y + current.panY - T) * ratio - target.y,
      });
    });
  };

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return undefined;

    const handleNativeWheel = (event: WheelEvent) => {
      event.preventDefault();
      event.stopPropagation();
      const anchor = screenToPlotPoint(event.clientX, event.clientY, svg, view);
      const factor = event.deltaY < 0 ? 1.14 : 0.88;
      setZoom(view.scale * factor, anchor);
    };

    svg.addEventListener('wheel', handleNativeWheel, { passive: false });
    return () => svg.removeEventListener('wheel', handleNativeWheel);
  }, [view]);

  const handlePointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { pointerId: event.pointerId, x: event.clientX, y: event.clientY, panX: view.panX, panY: view.panY, moved: false };
  };

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const drag = dragRef.current;
    const svg = svgRef.current;
    if (!drag || drag.pointerId !== event.pointerId || !svg || view.scale <= 1) return;
    const rect = svg.getBoundingClientRect();
    if (Math.hypot(event.clientX - drag.x, event.clientY - drag.y) > 3) drag.moved = true;
    setView(constrainView({
      scale: view.scale,
      panX: drag.panX + ((event.clientX - drag.x) / rect.width) * W / view.scale,
      panY: drag.panY + ((event.clientY - drag.y) / rect.height) * H / view.scale,
    }));
  };

  const endDrag = (event: React.PointerEvent<SVGSVGElement>) => {
    if (dragRef.current?.pointerId === event.pointerId) {
      suppressClickRef.current = dragRef.current.moved;
      dragRef.current = null;
    }
  };

  return (
    <PanelCard
      title="Sector Rotation · RRG"
      status={panel.status}
      subtitle="Relative strength vs S&P 500 · weekly · clockwise = rotation cycle"
      style={{ flex: 1.55, minWidth: 420, alignSelf: 'stretch', minHeight: 520, height: 'auto' }}
      right={
        <>
          <span style={{ fontFamily: mono, fontSize: 9, color: MM.dim, whiteSpace: 'nowrap' }}>
            X {formatAxisValue(visibleXMin)}..{formatAxisValue(visibleXMax)} · Y {formatAxisValue(visibleYMin)}..{formatAxisValue(visibleYMax)}
          </span>
          <div style={{ display: 'flex', border: `1px solid ${MM.border}`, borderRadius: 8, overflow: 'hidden' }}>
            {RRG_MODES.map(({ mode: m, label, title }) => {
              const active = mode === m;
              return (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  title={title}
                  style={{
                    cursor: active ? 'default' : 'pointer',
                    border: 'none',
                    background: active ? 'rgba(254,252,244,.08)' : 'transparent',
                    color: active ? MM.text : MM.dimmer,
                    padding: '5px 8px',
                    font: `${active ? 700 : 500} 9px Inter`,
                    letterSpacing: '.08em',
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <button
            onClick={() => setView({ scale: 1, panX: 0, panY: 0 })}
            disabled={!isZoomed}
            title="Reset zoom and pan"
            style={{
              cursor: isZoomed ? 'pointer' : 'default',
              border: `1px solid ${MM.border}`,
              background: isZoomed ? 'rgba(254,252,244,.04)' : 'transparent',
              color: isZoomed ? MM.muted : MM.dimmer,
              borderRadius: 8,
              padding: '5px 9px',
              font: '600 9px Inter',
              letterSpacing: '.08em',
              textTransform: 'uppercase',
            }}
          >
            Reset
          </button>
        </>
      }
    >
      {note && (
        <div style={{ fontSize: 11.5, color: MM.textSoft, fontStyle: 'italic', margin: '2px 0 8px', lineHeight: 1.5 }}>
          <span style={{ color: '#8fb8e8' }}>✦ </span>
          {note}
        </div>
      )}
      <div style={{ flex: '1 1 0', minHeight: 0, height: 0, display: 'flex', alignItems: 'stretch', justifyContent: 'center', overflow: 'hidden' }}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
          onPointerLeave={() => setHoveredSymbol(null)}
          onMouseLeave={() => setHoveredSymbol(null)}
          style={{
            width: '100%',
            height: '100%',
            minHeight: 0,
            maxHeight: '100%',
            display: 'block',
            cursor: isZoomed ? 'grab' : 'zoom-in',
            touchAction: 'none',
            userSelect: 'none',
          }}
        >
          <defs>
            <clipPath id={clipId}>
              <rect x={L} y={T} width={W - L - R} height={H - T - B} />
            </clipPath>
          </defs>
          <g clipPath={`url(#${clipId})`} transform={plotTransform}>
            <rect x={cx} y={T} width={W - R - cx} height={cy - T} fill="rgba(251,148,35,.045)" />
            <rect x={L} y={T} width={cx - L} height={cy - T} fill="rgba(254,252,244,.018)" />
            <rect x={L} y={cy} width={cx - L} height={H - B - cy} fill="rgba(254,252,244,.01)" />
            <line x1={L} y1={cy} x2={W - R} y2={cy} stroke="rgba(254,252,244,.14)" strokeWidth={1 / view.scale} />
            <line x1={cx} y1={T} x2={cx} y2={H - B} stroke="rgba(254,252,244,.14)" strokeWidth={1 / view.scale} />
            {axisTicks(domX).map((tick) => {
              const x = sx(tick);
              return (
                <g key={`x-${tick}`}>
                  <line x1={x} y1={cy - 4 / view.scale} x2={x} y2={cy + 4 / view.scale} stroke="rgba(254,252,244,.13)" strokeWidth={1 / view.scale} />
                  <text x={x} y={cy + 16 / view.scale} fill={MM.dimmer} fontSize={8.5 / view.scale} fontFamily={mono} textAnchor="middle">
                    {formatAxisValue(tick)}
                  </text>
                </g>
              );
            })}
            {axisTicks(domY).map((tick) => {
              const y = sy(tick);
              return (
                <g key={`y-${tick}`}>
                  <line x1={cx - 4 / view.scale} y1={y} x2={cx + 4 / view.scale} y2={y} stroke="rgba(254,252,244,.13)" strokeWidth={1 / view.scale} />
                  <text x={cx + 8 / view.scale} y={y - 4 / view.scale} fill={MM.dimmer} fontSize={8.5 / view.scale} fontFamily={mono}>
                    {formatAxisValue(tick)}
                  </text>
                </g>
              );
            })}
            <text x={W - R - 8 / view.scale} y={cy - 7 / view.scale} fill={MM.dim} fontSize={8.5 / view.scale} fontFamily={mono} textAnchor="end">
              RS-Ratio
            </text>
            <text x={cx + 8 / view.scale} y={T + 12 / view.scale} fill={MM.dim} fontSize={8.5 / view.scale} fontFamily={mono}>
              RS-Momentum
            </text>
            {[
              ['LEADING', W - R - 8, T + 14, 'end', MM.accent],
              ['IMPROVING', L + 8, T + 14, 'start', MM.muted],
              ['WEAKENING', W - R - 8, H - B - 7, 'end', MM.muted],
              ['LAGGING', L + 8, H - B - 7, 'start', MM.dim],
            ].map((q, i) => (
              <text key={i} x={q[1] as number} y={q[2] as number} fill={q[4] as string} fontSize={9 / view.scale} letterSpacing=".14em" fontWeight={600} fontFamily="Inter" textAnchor={q[3] as 'start' | 'end'} opacity={0.85}>
                {q[0] as string}
              </text>
            ))}
            {renderedSectors.map((s) => {
              const tail = s.pts.map((p) => ({ x: sx(p.x), y: sy(p.y) }));
              if (!tail.length) return null;
              const head = tail[tail.length - 1];
              const color = rrgColor(s.symbol, allSymbols);
              const active = activeSymbol === s.symbol;
              const dimmed = activeSymbol && !active;
              return (
                <g
                  key={s.symbol}
                  onClick={(event) => {
                    event.stopPropagation();
                    if (suppressClickRef.current) {
                      suppressClickRef.current = false;
                      return;
                    }
                    onOpen(s.symbol);
                  }}
                  onPointerEnter={() => setHoveredSymbol(s.symbol)}
                  onMouseEnter={() => setHoveredSymbol(s.symbol)}
                  style={{ cursor: 'pointer' }}
                >
                  <path d={smoothPath(tail)} fill="none" stroke="transparent" strokeWidth={14 / view.scale} strokeLinecap="round" />
                  <path d={smoothPath(tail)} fill="none" stroke={color} strokeWidth={(active ? 3 : 1.5) / view.scale} strokeLinecap="round" opacity={dimmed ? 0.22 : active ? 0.95 : 0.6} />
                  {tail.slice(0, -1).map((tp, ti) => (
                    <circle key={ti} cx={tp.x} cy={tp.y} r={(active ? 2.3 : 1.7) / view.scale} fill={color} opacity={dimmed ? 0.18 : (ti / tail.length) * 0.6 + 0.15} />
                  ))}
                  <circle cx={head.x} cy={head.y} r={(active ? 6 : 4.8) / view.scale} fill="#0c0c0d" stroke={color} strokeWidth={(active ? 2.5 : 1.8) / view.scale} />
                  <text x={head.x + 8 / view.scale} y={head.y + 3 / view.scale} fill={color} fontSize={9.5 / view.scale} fontWeight={700} fontFamily={mono} opacity={dimmed ? 0.3 : 1}>
                    {s.symbol}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      {sectors.length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, borderTop: `1px solid ${MM.border}`, paddingTop: 10, marginTop: 10 }}>
          {sectors.map((s) => {
            const color = rrgColor(s.symbol, allSymbols);
            const active = activeSymbol === s.symbol;
            const pinned = pinnedSymbol === s.symbol;
            return (
              <button
                key={s.symbol}
                type="button"
                onClick={() => setPinnedSymbol((current) => (current === s.symbol ? null : s.symbol))}
                onMouseEnter={() => setHoveredSymbol(s.symbol)}
                onMouseLeave={() => setHoveredSymbol(null)}
                onPointerEnter={() => setHoveredSymbol(s.symbol)}
                onPointerLeave={() => setHoveredSymbol(null)}
                title={`${s.name} · ${s.quadrant}${pinned ? ' · pinned' : ''}`}
                style={{
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  border: `1px solid ${active ? color : MM.border}`,
                  background: active ? 'rgba(254,252,244,.045)' : 'transparent',
                  color: active ? MM.text : MM.muted,
                  borderRadius: 8,
                  padding: '5px 8px',
                  fontFamily: mono,
                  fontSize: 10.5,
                  fontWeight: active ? 700 : 500,
                  lineHeight: 1,
                  opacity: activeSymbol && !active ? 0.48 : 1,
                }}
              >
                <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, boxShadow: pinned ? `0 0 0 3px rgba(254,252,244,.08)` : 'none' }} />
                {s.symbol}
              </button>
            );
          })}
        </div>
      )}
    </PanelCard>
  );
}
