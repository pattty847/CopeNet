import { useId, useMemo, useState } from 'react';
import type { Panel, RrgMode, RrgSector } from './types';
import { MM, PanelCard, mono } from './marketUi';
import { useIsMobile } from '../../lib/responsive';
import { useRrgInteraction } from './useRrgInteraction';
import { W, H, L, R, T, B, MIN_SCALE, MAX_SCALE, smoothPath, rrgColor, axisTicks, formatAxisValue, rrgLabelSize } from './rrgGeometry';

const RRG_MODES: { mode: RrgMode; label: string; title: string }[] = [
  { mode: 'fast', label: 'FAST', title: 'Fast · 8w level · 2w momentum · EMA 2' },
  { mode: 'default', label: 'STD', title: 'Standard · 13w level · 4w momentum · EMA 3' },
  { mode: 'slow', label: 'SLOW', title: 'Slow · 26w level · 8w momentum · EMA 5' },
];

export function Rrg({
  panel,
  onOpen,
  note,
  title = 'Sector Rotation · RRG',
  subtitle = 'Relative strength vs S&P 500 · weekly · clockwise = rotation cycle',
}: {
  panel: Panel<RrgSector[]>;
  onOpen: (s: string) => void;
  note?: string;
  /** Overridden by the industry chart, which is the same component over a different basket. */
  title?: string;
  subtitle?: string;
}) {
  const isMobile = useIsMobile();
  const clipId = useId();
  const { svgRef, view, setView, setZoom, pixelScale, touchPan, setTouchPan, suppressClickRef, handlePointerDown, handlePointerMove, endDrag } = useRrgInteraction();
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


  return (
    <PanelCard
      title={title}
      status={panel.status}
      subtitle={subtitle}
      style={{
        // Mobile: flex-basis 100% claims a full wrap line (width alone loses to flex-basis:0,
        // which let this panel get crushed into a sliver beside the Accumulation column).
        flex: isMobile ? '1 1 100%' : 1.55,
        minWidth: isMobile ? 0 : 420,
        alignSelf: 'stretch',
        // Desktop gets a floor to fill its grid cell. Mobile must NOT: a min-height-only card
        // has no definite height, so the aspect-sized chart below would be padded out by
        // whatever the floor exceeded — and the plot itself never grows to meet it.
        minHeight: 0,
        height: 'auto',
      }}
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
                    font: `${active ? 700 : 500} 9px var(--mkt-sans)`,
                    letterSpacing: '.08em',
                  }}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <button type="button" className="tw-btn" aria-label="Zoom out RRG" disabled={!isZoomed} onClick={() => setZoom(view.scale / 1.25)}>−</button>
          <button type="button" className="tw-btn" aria-label="Zoom in RRG" disabled={view.scale >= MAX_SCALE} onClick={() => setZoom(view.scale * 1.25)}>+</button>
          {isMobile && <button type="button" className="tw-btn" aria-pressed={touchPan} onClick={() => setTouchPan(!touchPan)}>{touchPan ? 'Done panning' : 'Pan chart'}</button>}
          <button
            onClick={() => { setView({ scale: MIN_SCALE, panX: 0, panY: 0 }); setTouchPan(false); }}
            disabled={!isZoomed}
            title="Reset zoom and pan"
            style={{
              cursor: isZoomed ? 'pointer' : 'default',
              border: `1px solid ${MM.border}`,
              background: isZoomed ? 'rgba(254,252,244,.04)' : 'transparent',
              color: isZoomed ? MM.muted : MM.dimmer,
              borderRadius: 8,
              padding: '5px 9px',
              font: '600 9px var(--mkt-sans)',
              letterSpacing: '.08em',
              textTransform: 'uppercase',
            }}
          >
            Reset
          </button>
        </>
      }
    >
      <span style={{ color: MM.dim, fontSize: 10, marginBottom: 4 }}>
        {isMobile ? (touchPan ? 'Drag to pan · Done panning restores page scroll' : 'Swipe to scroll · + / − to zoom') : 'Scroll the page · Ctrl/⌘ + wheel to zoom · drag to pan'}
      </span>
      {/* The plot sizes from its viewBox aspect ratio so it never depends on the card resolving
          a height: width decides, and two charts side by side come out the same size. */}
      <div style={{ flex: '0 0 auto', minHeight: 0, height: 'auto', display: 'flex', alignItems: 'stretch', justifyContent: 'center', overflow: 'hidden' }}>
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
            height: 'auto',
            minHeight: 0,
            aspectRatio: `${W} / ${H}`,
            display: 'block',
            cursor: isZoomed ? 'grab' : 'default',
            touchAction: touchPan ? 'none' : 'pan-y pinch-zoom',
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
              <text key={i} x={q[1] as number} y={q[2] as number} fill={q[4] as string} fontSize={10 / view.scale} letterSpacing=".14em" fontWeight={600} fontFamily="var(--mkt-sans)" textAnchor={q[3] as 'start' | 'end'} opacity={0.85}>
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
                  <text x={head.x + 8 / view.scale} y={head.y + 3.5 / view.scale} fill={color} fontSize={rrgLabelSize(active, view.scale, pixelScale)} fontWeight={700} fontFamily={mono} opacity={dimmed ? 0.3 : 1}>
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
      {note && (
        <div style={{ fontSize: 11.5, color: MM.textSoft, fontStyle: 'italic', margin: '10px 0 0', lineHeight: 1.5, borderLeft: '2px solid rgba(143,184,232,.35)', paddingLeft: 10 }}>
          <span style={{ color: '#8fb8e8' }}>✦ </span>
          {note}
        </div>
      )}
    </PanelCard>
  );
}
