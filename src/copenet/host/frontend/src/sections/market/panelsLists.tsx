import type {
  AccumulationRow,
  ContrarianNote,
  EvidenceItem,
  Panel,
  Portfolio as PortfolioData,
  SoftBottomItem,
  SpecPosition,
  TrendRow,
} from './types';
import { EvidenceFlagBadge, EvidenceToneGlyph, MM, PanelCard, evidenceDate, evidenceTypeBg, evidenceTypeColor, label, mono, toneColor, valueTone } from './marketUi';

export function SoftBottomingWatch({ panel, onOpen }: { panel: Panel<SoftBottomItem[]>; onOpen: (s: string) => void }) {
  return (
    <PanelCard
      title="Soft Bottoming Watch"
      status={panel.status}
      subtitle={panel.note || 'names putting in a base — calibrated against real history'}
      right={<span style={{ fontSize: 10, color: MM.dim }}>calibrated · 8w</span>}
    >
      {panel.data.length === 0 ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>No names flagged right now — soft bottoming is rare by design.</div>
      ) : (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 9 }}>
          {panel.data.map((s) => (
            <button
              key={s.symbol}
              onClick={() => onOpen(s.symbol)}
              title={s.name}
              style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 9, border: `1px solid rgba(105,197,137,.22)`, background: 'rgba(105,197,137,.06)', borderRadius: 11, padding: '8px 12px', textAlign: 'left' }}
            >
              <span style={{ width: 7, height: 7, borderRadius: '50%', background: MM.up, flex: '0 0 auto' }} />
              <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 600, color: MM.text }}>{s.symbol}</span>
              <span style={{ fontFamily: mono, fontSize: 10.5, color: MM.up }}>{s.score.toFixed(2)}</span>
              <span style={{ fontFamily: mono, fontSize: 10.5, color: MM.dim }}>{s.drawdown} dd · RSI {s.rsi}</span>
            </button>
          ))}
        </div>
      )}
    </PanelCard>
  );
}

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
      <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 360, overflowY: 'auto', paddingRight: 4 }}>
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
              <span style={{ color: valueTone(r.belowMa) }}>{r.belowMa} <span style={{ color: MM.dimmer }}>vs 50W</span></span>
              <span style={{ color: valueTone(r.drawdown) }}>{r.drawdown} <span style={{ color: MM.dimmer }}>drawdn</span></span>
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
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9, maxHeight: 240, overflowY: 'auto', paddingRight: 4 }}>
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

export function Portfolio({
  panel,
  onOpen,
  onSyncWebull,
  syncing,
}: {
  panel: Panel<PortfolioData>;
  onOpen: (s: string) => void;
  onSyncWebull?: () => void;
  syncing?: boolean;
}) {
  const p = panel.data;
  const fromWebull = (panel.note || '').toLowerCase().includes('webull');
  return (
    <PanelCard
      title="Portfolio · live P&L"
      status={panel.status}
      subtitle={panel.note || 'Disciplined core · live P&L'}
      style={{ flex: 1.4, minWidth: 380 }}
      right={
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {onSyncWebull && (
            <button
              onClick={onSyncWebull}
              disabled={syncing}
              title={fromWebull ? 'Re-sync positions from Webull (read-only)' : 'Sync positions from Webull (read-only)'}
              style={{ cursor: syncing ? 'default' : 'pointer', border: `1px solid ${MM.border}`, background: 'transparent', color: MM.muted, borderRadius: 8, padding: '5px 10px', font: '600 9px var(--mkt-sans)', letterSpacing: '.08em', textTransform: 'uppercase', opacity: syncing ? 0.6 : 1 }}
            >
              {syncing ? '◍ Syncing…' : '↻ Webull'}
            </button>
          )}
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontFamily: mono, fontSize: 17, color: MM.text }}>{p.total}</div>
            <div style={{ fontFamily: mono, fontSize: 11, color: toneColor(p.pnlTone) }}>{p.pnl}</div>
          </div>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, paddingBottom: 6, font: '600 8.5px var(--mkt-sans)', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dimmer }}>
          <span style={{ width: 54 }} />
          <span style={{ flex: 1 }}>Position</span>
          <span style={{ width: 74, textAlign: 'right' }}>Price</span>
          <span style={{ width: 78, textAlign: 'right' }}>Value</span>
          <span style={{ width: 52, textAlign: 'right' }}>Book</span>
          <span style={{ width: 64, textAlign: 'right' }}>P&L</span>
        </div>
        {(() => {
          const money = (s: string) => {
            const n = parseFloat(s.replace(/[^0-9.\-]/g, ''));
            return Number.isFinite(n) ? n : null;
          };
          const values = p.positions.map((pos) => {
            const last = money(pos.last);
            return last != null && pos.shares ? last * pos.shares : null;
          });
          const book = values.reduce<number>((acc, v) => acc + (v ?? 0), 0);
          return p.positions.map((pos, i) => {
            const value = values[i];
            const alloc = value != null && book > 0 ? (value / book) * 100 : null;
            return (
              <button key={pos.symbol} onClick={() => onOpen(pos.symbol)} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12, padding: '9px 0', borderTop: `1px solid rgba(254,252,244,.05)`, background: 'transparent', border: 'none', borderTopColor: 'rgba(254,252,244,.05)', textAlign: 'left' }}>
                <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 600, color: MM.text, width: 54 }}>{pos.symbol}</span>
                <span style={{ flex: 1, fontFamily: mono, fontSize: 10.5, color: MM.dim }}>{pos.shares ? `${pos.shares} sh @ ${pos.avgCost}` : 'add cost basis'}</span>
                <span style={{ fontFamily: mono, fontSize: 12, color: MM.text, width: 74, textAlign: 'right' }}>{pos.last}</span>
                <span style={{ fontFamily: mono, fontSize: 12, color: MM.textSoft, width: 78, textAlign: 'right' }}>{value != null ? `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}` : '—'}</span>
                <span style={{ fontFamily: mono, fontSize: 11, color: MM.muted, width: 52, textAlign: 'right' }}>{alloc != null ? `${alloc.toFixed(0)}%` : '—'}</span>
                <span style={{ fontFamily: mono, fontSize: 12, color: toneColor(pos.tone), width: 64, textAlign: 'right' }}>{pos.pnlPct}</span>
              </button>
            );
          });
        })()}
      </div>
    </PanelCard>
  );
}

export function Speculative({ panel, onOpen, comment }: { panel: Panel<SpecPosition[]>; onOpen: (s: string) => void; comment?: string }) {
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
        <span style={{ borderRadius: 999, border: `1px solid rgba(251,148,35,.28)`, padding: '2px 8px', font: '600 8px var(--mkt-sans)', letterSpacing: '.12em', textTransform: 'uppercase', color: MM.accent }}>sized small</span>
      </div>
      <div style={{ fontSize: 11, color: MM.faint, marginBottom: 13, fontStyle: 'italic' }}>Separate from the core. Every position has a defined exit.</div>
      {comment && (
        <div style={{ fontSize: 11.5, color: MM.textSoft, fontStyle: 'italic', marginBottom: 12, lineHeight: 1.5, borderLeft: `2px solid rgba(90,143,199,.35)`, paddingLeft: 10 }}>
          <span style={{ color: '#8fb8e8' }}>✦ </span>
          {comment}
        </div>
      )}
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
