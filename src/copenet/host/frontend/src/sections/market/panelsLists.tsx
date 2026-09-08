import type { Panel, Portfolio as PortfolioData, SpecPosition } from './types';
import { EvidenceFlagBadge, EvidenceToneGlyph, MM, PanelCard, evidenceDate, evidenceTypeBg, evidenceTypeColor, label, mono, toneColor, valueTone } from './marketUi';

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
