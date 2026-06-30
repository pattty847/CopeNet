import type { Briefing, MacroItem, Panel, RrgSector } from './types';
import { MM, PanelCard, PreviewBadge, label, mono, toneColor } from './marketUi';

function Sparkline({ data, tone }: { data: number[]; tone: 'up' | 'down' | 'flat' }) {
  const w = 58;
  const h = 20;
  const mn = Math.min(...data);
  const mx = Math.max(...data);
  const rg = mx - mn || 1;
  const pts = data.map((y, i) => [(i / (data.length - 1)) * w, h - 2 - ((y - mn) / rg) * (h - 4)]);
  const d = 'M' + pts.map((p) => `${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' L');
  const col = toneColor(tone);
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`} style={{ display: 'block' }}>
      <path d={d} fill="none" stroke={col} strokeWidth={1.4} strokeLinecap="round" strokeLinejoin="round" opacity={0.9} />
      <circle cx={pts[pts.length - 1][0]} cy={pts[pts.length - 1][1]} r={1.8} fill={col} />
    </svg>
  );
}

export function BriefingHero({ panel, onOpen, onExplain }: { panel: Panel<Briefing>; onOpen: (s: string) => void; onExplain: () => void }) {
  const b = panel.data;
  const [before, after] = b.emphasis && b.headline.includes(b.emphasis) ? b.headline.split(b.emphasis) : [b.headline, ''];
  return (
    <div
      style={{
        position: 'relative',
        overflow: 'hidden',
        border: `1px solid ${MM.border}`,
        borderRadius: 16,
        background: `radial-gradient(130% 150% at 90% -30%, rgba(251,148,35,.11), transparent 52%), ${MM.panel}`,
        padding: '26px 28px',
        display: 'flex',
        gap: 30,
        alignItems: 'stretch',
        flexWrap: 'wrap',
      }}
    >
      <div style={{ flex: 1, minWidth: 320 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 11, flexWrap: 'wrap' }}>
          <span style={{ ...label, fontSize: 9.5, letterSpacing: '.16em' }}>Daily Briefing</span>
          <span
            style={{
              borderRadius: 999,
              border: `1px solid rgba(251,148,35,.28)`,
              background: MM.accentSoft,
              padding: '3px 9px',
              font: '600 9px Inter',
              letterSpacing: '.13em',
              textTransform: 'uppercase',
              color: MM.accent,
            }}
          >
            Risk-on · late cycle
          </span>
          <PreviewBadge status={panel.status} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', marginBottom: 15 }}>
          <span style={{ font: '600 8.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.dim }}>What changed</span>
          {b.changed.map((ch, i) => (
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 11.5, color: MM.textSoft }}>
              <span style={{ width: 4, height: 4, borderRadius: '50%', background: toneColor(ch.tone) }} />
              {ch.text}
            </span>
          ))}
        </div>
        <div onClick={onExplain} title="See why this read" style={{ cursor: 'pointer', marginBottom: 16 }}>
          <h1 style={{ margin: '0 0 12px', fontFamily: "'Cormorant Garamond', serif", fontWeight: 600, fontSize: 38, lineHeight: 1.08, letterSpacing: '-.01em', color: MM.text, maxWidth: 760 }}>
            {before}
            {after && <span style={{ color: MM.accent }}>{b.emphasis}</span>}
            {after}
          </h1>
          <p style={{ margin: '0 0 8px', fontSize: 14, lineHeight: 1.6, color: MM.muted, maxWidth: 640 }}>{b.summary}</p>
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, font: '600 10px Inter', letterSpacing: '.06em', textTransform: 'uppercase', color: MM.accent }}>Why this read →</span>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 9 }}>
          {b.attention.map((a, i) => (
            <button
              key={i}
              onClick={() => onOpen(a.symbol)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 9,
                cursor: 'pointer',
                border: `1px solid rgba(254,252,244,.08)`,
                background: MM.panelInset,
                borderRadius: 11,
                padding: '8px 13px 8px 10px',
                textAlign: 'left',
              }}
            >
              <span style={{ width: 24, height: 24, borderRadius: 7, background: MM.accentSoft, color: MM.accent, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11 }}>{a.glyph}</span>
              <span style={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
                <span style={{ font: '600 9px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dim }}>{a.kind}</span>
                <span style={{ fontSize: 12.5, fontWeight: 500, color: MM.text }}>{a.label}</span>
              </span>
            </button>
          ))}
        </div>
      </div>
      <div style={{ flex: '0 0 210px', borderLeft: `1px solid ${MM.border}`, paddingLeft: 26, display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 16 }}>
        <span style={{ ...label, letterSpacing: '.14em' }}>Regime read</span>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {/* regime scale is illustrative until backend lands */}
          {[
            { name: 'Risk-off', active: false, note: '' },
            { name: 'Chop', active: false, note: '' },
            { name: 'Risk-on', active: true, note: 'now' },
            { name: 'Event-risk', active: false, note: 'CPI Thu' },
          ].map((r) => (
            <div key={r.name} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: r.active ? MM.accent : 'rgba(254,252,244,.14)', flex: '0 0 8px' }} />
              <span style={{ flex: 1, fontSize: 12, color: r.active ? MM.text : MM.dim, fontWeight: r.active ? 600 : 400 }}>{r.name}</span>
              <span style={{ fontFamily: mono, fontSize: 10, color: MM.dim }}>{r.note}</span>
            </div>
          ))}
        </div>
        <div style={{ borderTop: `1px solid ${MM.border}`, paddingTop: 12, display: 'flex', gap: 18 }}>
          <div>
            <div style={{ fontFamily: mono, fontSize: 17, color: MM.text }}>{b.vix}</div>
            <div style={{ font: '600 8.5px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dim, marginTop: 2 }}>VIX</div>
          </div>
          <div>
            <div style={{ fontFamily: mono, fontSize: 17, color: MM.up }}>{b.breadthPct}%</div>
            <div style={{ font: '600 8.5px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dim, marginTop: 2 }}>Breadth</div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function MacroBoard({ panel }: { panel: Panel<MacroItem[]> }) {
  return (
    <PanelCard title="Macro Board — what's the weather" status={panel.status} right={<span style={{ fontSize: 11, color: MM.dim, fontStyle: 'italic' }}>5-day · close</span>}>
      <div style={{ display: 'flex', flexWrap: 'wrap' }}>
        {panel.data.map((m, i) => (
          <div key={i} style={{ flex: 1, minWidth: 120, padding: '0 16px', borderRight: i < panel.data.length - 1 ? `1px solid rgba(254,252,244,.05)` : 'none', display: 'flex', flexDirection: 'column', gap: 7 }}>
            <span style={{ font: '600 9px Inter', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.dim }}>{m.label}</span>
            <div style={{ fontFamily: mono, fontSize: 18, color: MM.text, letterSpacing: '-.02em' }}>{m.value}</div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
              <span style={{ fontFamily: mono, fontSize: 11, color: toneColor(m.tone) }}>{m.change}</span>
              <Sparkline data={m.spark} tone={m.tone} />
            </div>
          </div>
        ))}
      </div>
    </PanelCard>
  );
}

/** Catmull-Rom → cubic bezier, so rotation tails read as smooth curves not jagged polylines. */
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

export function Rrg({ panel, onOpen }: { panel: Panel<RrgSector[]>; onOpen: (s: string) => void }) {
  const W = 560;
  const H = 430;
  const L = 42;
  const R = 20;
  const T = 18;
  const B = 30;
  const TAIL = 4; // most-recent N points = a readable rotation cycle without spaghetti
  const sectors = panel.data.map((s) => ({ ...s, pts: s.tail.slice(-TAIL) }));
  // The backend's RS-Ratio (% deviation) and RS-Momentum (z-score) live on different scales, so a
  // fixed domain pushed points off-canvas. Auto-fit each axis to the real data; keep 0 centered so
  // the quadrants stay meaningful; clamp outliers to the box edge.
  const xs = sectors.flatMap((s) => s.pts.map((p) => Math.abs(p.x)));
  const ys = sectors.flatMap((s) => s.pts.map((p) => Math.abs(p.y)));
  const domX = Math.max(1, ...xs) * 1.12;
  const domY = Math.max(1, ...ys) * 1.12;
  const clamp = (v: number, d: number) => Math.max(-d, Math.min(d, v));
  const sx = (x: number) => L + ((clamp(x, domX) + domX) / (2 * domX)) * (W - L - R);
  const sy = (y: number) => T + ((domY - clamp(y, domY)) / (2 * domY)) * (H - T - B);
  const cx = sx(0);
  const cy = sy(0);
  return (
    <PanelCard
      title="Sector Rotation · RRG"
      status={panel.status}
      subtitle="Relative strength vs S&P 500 · weekly · clockwise = rotation cycle"
      style={{ flex: 1.55, minWidth: 420, alignSelf: 'flex-start' }}
    >
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height: 'auto', maxHeight: 420, display: 'block' }}>
          <defs>
            <clipPath id="rrgClip">
              <rect x={L} y={T} width={W - L - R} height={H - T - B} />
            </clipPath>
          </defs>
          <rect x={cx} y={T} width={W - R - cx} height={cy - T} fill="rgba(251,148,35,.045)" />
          <rect x={L} y={T} width={cx - L} height={cy - T} fill="rgba(254,252,244,.018)" />
          <rect x={L} y={cy} width={cx - L} height={H - B - cy} fill="rgba(254,252,244,.01)" />
          <line x1={L} y1={cy} x2={W - R} y2={cy} stroke="rgba(254,252,244,.14)" strokeWidth={1} />
          <line x1={cx} y1={T} x2={cx} y2={H - B} stroke="rgba(254,252,244,.14)" strokeWidth={1} />
          {[
            ['LEADING', W - R - 8, T + 14, 'end', MM.accent],
            ['IMPROVING', L + 8, T + 14, 'start', MM.muted],
            ['WEAKENING', W - R - 8, H - B - 7, 'end', MM.muted],
            ['LAGGING', L + 8, H - B - 7, 'start', MM.dim],
          ].map((q, i) => (
            <text key={i} x={q[1] as number} y={q[2] as number} fill={q[4] as string} fontSize={9} letterSpacing=".14em" fontWeight={600} fontFamily="Inter" textAnchor={q[3] as 'start' | 'end'} opacity={0.85}>
              {q[0] as string}
            </text>
          ))}
          {sectors.map((s) => {
            const tail = s.pts.map((p) => ({ x: sx(p.x), y: sy(p.y) }));
            if (!tail.length) return null;
            const head = tail[tail.length - 1];
            return (
              <g key={s.symbol} style={{ cursor: 'pointer' }} onClick={() => onOpen(s.symbol)}>
                <path d={smoothPath(tail)} clipPath="url(#rrgClip)" fill="none" stroke="rgba(254,252,244,.13)" strokeWidth={1.2} strokeLinecap="round" />
                {tail.slice(0, -1).map((tp, ti) => (
                  <circle key={ti} cx={tp.x} cy={tp.y} r={1.4} fill={MM.text} opacity={(ti / tail.length) * 0.4} />
                ))}
                <circle cx={head.x} cy={head.y} r={4.6} fill="#0c0c0d" stroke={MM.text} strokeWidth={1.6} />
                <text x={head.x + 8} y={head.y + 3} fill={MM.textSoft} fontSize={9.5} fontWeight={600} fontFamily={mono}>
                  {s.symbol}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </PanelCard>
  );
}
