import type {
  AccumulationRow,
  ContrarianNote,
  EvidenceItem,
  Panel,
  Portfolio as PortfolioData,
  SpecPosition,
  TrendRow,
} from './types';
import { MM, PanelCard, label, mono, toneColor } from './marketUi';

function ConfDots({ n }: { n: number }) {
  return (
    <span style={{ display: 'inline-flex', gap: 3, alignItems: 'center' }}>
      {[0, 1, 2, 3].map((i) => (
        <span key={i} style={{ width: 5, height: 5, borderRadius: '50%', background: i < n ? MM.accent : 'rgba(254,252,244,.12)' }} />
      ))}
    </span>
  );
}

export function AccumulationWatch({ panel, onOpen }: { panel: Panel<AccumulationRow[]>; onOpen: (s: string) => void }) {
  return (
    <PanelCard title="Accumulation Watch" status={panel.status} subtitle="Quality names sitting in pullback zones — add candidates" right={<span style={{ fontSize: 10, color: MM.dim }}>confluence ranked</span>}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {panel.data.map((r) => (
          <button key={r.symbol} onClick={() => onOpen(r.symbol)} style={{ cursor: 'pointer', padding: '10px 0', borderTop: `1px solid rgba(254,252,244,.05)`, background: 'transparent', border: 'none', borderTopColor: 'rgba(254,252,244,.05)', textAlign: 'left', width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 9, minWidth: 0 }}>
                <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 600, color: MM.text }}>{r.symbol}</span>
                <span style={{ fontSize: 11.5, color: MM.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{r.name}</span>
              </div>
              <ConfDots n={r.confluence} />
            </div>
            <div style={{ display: 'flex', gap: 14, marginTop: 6, fontFamily: mono, fontSize: 10.5, color: MM.dim }}>
              <span>{r.belowMa} <span style={{ color: MM.dimmer }}>vs 50W</span></span>
              <span>{r.drawdown} <span style={{ color: MM.dimmer }}>drawdn</span></span>
              <span>RSI {r.rsi}</span>
            </div>
            <div style={{ fontSize: 11, color: MM.faint, marginTop: 5, lineHeight: 1.45 }}>{r.why}</div>
          </button>
        ))}
      </div>
    </PanelCard>
  );
}

export function TrendWatch({ panel, onOpen }: { panel: Panel<TrendRow[]>; onOpen: (s: string) => void }) {
  return (
    <PanelCard title="Trend-Change Watch" status={panel.status} right={<span style={{ fontSize: 10, color: MM.dim }}>weekly · daily-confirmed</span>}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {panel.data.map((t) => {
          const up = t.direction === 'up';
          return (
            <button key={t.symbol} onClick={() => onOpen(t.symbol)} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 11, background: 'transparent', border: 'none', padding: 0, textAlign: 'left' }}>
              <span style={{ width: 22, height: 22, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, background: up ? 'rgba(105,197,137,.12)' : 'rgba(217,109,95,.12)', color: up ? MM.up : MM.down }}>{up ? '↑' : '↓'}</span>
              <span style={{ fontFamily: mono, fontSize: 12.5, fontWeight: 600, color: MM.text, width: 46 }}>{t.symbol}</span>
              <span style={{ flex: 1, fontSize: 11.5, color: MM.muted }}>{t.note}</span>
              <span style={{ fontFamily: mono, fontSize: 10, color: MM.dim }}>{t.when}</span>
            </button>
          );
        })}
        <div style={{ borderTop: `1px solid rgba(254,252,244,.05)`, paddingTop: 9, fontSize: 11, color: MM.faint, fontStyle: 'italic' }}>Only names with daily confirmation are flagged.</div>
      </div>
    </PanelCard>
  );
}

export function Portfolio({ panel, onOpen }: { panel: Panel<PortfolioData>; onOpen: (s: string) => void }) {
  const p = panel.data;
  return (
    <PanelCard
      title="Portfolio · live P&L"
      status={panel.status}
      subtitle="Disciplined core · cost basis pending"
      style={{ flex: 1.4, minWidth: 380 }}
      right={
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontFamily: mono, fontSize: 17, color: MM.text }}>{p.total}</div>
          <div style={{ fontFamily: mono, fontSize: 11, color: toneColor(p.pnlTone) }}>{p.pnl}</div>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {p.positions.map((pos) => (
          <button key={pos.symbol} onClick={() => onOpen(pos.symbol)} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12, padding: '9px 0', borderTop: `1px solid rgba(254,252,244,.05)`, background: 'transparent', border: 'none', borderTopColor: 'rgba(254,252,244,.05)', textAlign: 'left' }}>
            <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 600, color: MM.text, width: 54 }}>{pos.symbol}</span>
            <span style={{ flex: 1, fontFamily: mono, fontSize: 10.5, color: MM.dim }}>{pos.shares ? `${pos.shares} sh @ ${pos.avgCost}` : 'add cost basis'}</span>
            <span style={{ fontFamily: mono, fontSize: 12, color: MM.text, width: 74, textAlign: 'right' }}>{pos.last}</span>
            <span style={{ fontFamily: mono, fontSize: 12, color: toneColor(pos.tone), width: 64, textAlign: 'right' }}>{pos.pnlPct}</span>
          </button>
        ))}
      </div>
    </PanelCard>
  );
}

export function Speculative({ panel, onOpen }: { panel: Panel<SpecPosition[]>; onOpen: (s: string) => void }) {
  return (
    <div
      style={{
        flex: 1,
        minWidth: 300,
        position: 'relative',
        border: `1px dashed rgba(251,148,35,.3)`,
        borderRadius: 14,
        padding: 16,
        background: `repeating-linear-gradient(135deg, rgba(251,148,35,.025) 0 12px, transparent 12px 24px), ${MM.panel}`,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <span style={{ ...label, color: MM.accent }}>⚠ Speculative lane</span>
        <span style={{ borderRadius: 999, border: `1px solid rgba(251,148,35,.28)`, padding: '2px 8px', font: '600 8px Inter', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.accent }}>sized small</span>
      </div>
      <div style={{ fontSize: 11, color: MM.faint, marginBottom: 13, fontStyle: 'italic' }}>Separate from the core. Every position has a defined exit.</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
        {panel.data.map((s) => (
          <button key={s.symbol} onClick={() => onOpen(s.symbol)} style={{ cursor: 'pointer', border: `1px solid ${MM.border}`, borderRadius: 10, padding: 11, background: 'transparent', textAlign: 'left' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 600, color: MM.text }}>{s.symbol}</span>
              <span style={{ fontFamily: mono, fontSize: 12, color: toneColor(s.tone) }}>{s.pnlPct}</span>
            </div>
            <div style={{ fontSize: 11, color: MM.faint, margin: '5px 0 8px', lineHeight: 1.4 }}>{s.thesis}</div>
            <div style={{ display: 'flex', gap: 6, fontFamily: mono, fontSize: 9.5 }}>
              <span style={{ flex: 1, textAlign: 'center', padding: '4px 0', borderRadius: 6, background: 'rgba(254,252,244,.04)', color: MM.muted }}>entry {s.entry}</span>
              <span style={{ flex: 1, textAlign: 'center', padding: '4px 0', borderRadius: 6, background: 'rgba(105,197,137,.08)', color: MM.up }}>tgt {s.target}</span>
              <span style={{ flex: 1, textAlign: 'center', padding: '4px 0', borderRadius: 6, background: 'rgba(217,109,95,.08)', color: MM.down }}>inval {s.invalidation}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

export function Evidence({ panel, onOpen }: { panel: Panel<EvidenceItem[]>; onOpen: (s: string) => void }) {
  const typeBg = (t: EvidenceItem['type']) => (t === 'Insider' ? MM.accentSoft : 'rgba(254,252,244,.06)');
  const typeColor = (t: EvidenceItem['type']) => (t === 'Insider' ? MM.accent : MM.textSoft);
  return (
    <PanelCard title="Evidence & News — why it moved" status={panel.status} style={{ flex: 1.4, minWidth: 380 }} right={<span style={{ fontSize: 10, color: MM.dim }}>cited · last 72h</span>}>
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {panel.data.map((e, i) => (
          <button key={i} onClick={() => onOpen(e.symbol)} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12, padding: '10px 0', borderTop: `1px solid rgba(254,252,244,.05)`, background: 'transparent', border: 'none', borderTopColor: 'rgba(254,252,244,.05)', textAlign: 'left' }}>
            <span style={{ flex: '0 0 auto', borderRadius: 6, padding: '3px 7px', font: '600 8.5px Inter', letterSpacing: '.08em', textTransform: 'uppercase', background: typeBg(e.type), color: typeColor(e.type) }}>{e.type}</span>
            <span style={{ fontFamily: mono, fontSize: 12, fontWeight: 600, color: MM.text, width: 50 }}>{e.symbol}</span>
            <span style={{ flex: 1, fontSize: 12, color: MM.textSoft, lineHeight: 1.4 }}>{e.headline}</span>
            <span style={{ fontSize: 10, color: MM.dim, whiteSpace: 'nowrap' }}>{e.source}</span>
          </button>
        ))}
      </div>
    </PanelCard>
  );
}

export function Contrarian({ panel }: { panel: Panel<ContrarianNote[]> }) {
  return (
    <div style={{ flex: 1, minWidth: 300, background: `linear-gradient(180deg, rgba(251,148,35,.05), transparent 40%), ${MM.panel}`, border: `1px solid rgba(251,148,35,.16)`, borderRadius: 14, padding: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
        <span style={{ color: MM.accent, fontSize: 11 }}>◆</span>
        <span style={{ ...label, color: MM.accent }}>Contrarian · thesis-killers</span>
      </div>
      <div style={{ fontSize: 11, color: MM.faint, marginBottom: 13, fontStyle: 'italic' }}>For every highlighted signal: what would make this wrong?</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {panel.data.map((c, i) => (
          <div key={i} style={{ borderLeft: `2px solid rgba(251,148,35,.3)`, paddingLeft: 12 }}>
            <div style={{ font: '600 9px Inter', letterSpacing: '.08em', textTransform: 'uppercase', color: MM.muted, marginBottom: 4 }}>{c.signal}</div>
            <div style={{ fontSize: 12, color: MM.textSoft, lineHeight: 1.5 }}>{c.kill}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
