// "Since you last looked" — the 60-second question-structured morning brief.
// Owns the first viewport (see docs/plans/MARKET_DESIGN_REVIEW.md §5): every row answers
// a standing question — REGIME (what world am I in), MATTERS (what changed that I care
// about), MOVERS (what moved), BOOK (my money), LEDGER (is any of this calibrated).
// Renders only deltas; the standing picture lives behind the Market detail expander.
// Honest empty states throughout — a quiet day says so instead of manufacturing news.

import { useState, type ReactNode } from 'react';
import { MM, evidenceDate, mono, toneColor } from './marketUi';
import type { LedgerReport, MorningBriefPayload, Panel, Regime, Tone } from './types';

const MATTERS_VISIBLE = 3;

const REGIME_COLOR: Record<string, string> = {
  'risk-on': MM.up,
  'risk-off': MM.down,
  chop: MM.muted,
  'event-risk': MM.accent,
};

interface MatterItem {
  key: string;
  kind: string;
  symbol: string;
  text: string;
  tone: Tone;
  t?: number | null;
  url?: string | null;
}

/** Rank what changed by how much it should interrupt a morning glance:
 *  flagged SEC evidence (clusters, high-signal 8-Ks) > signal flips > rotation
 *  moves > the rest of the new filings. */
function composeMatters(brief: MorningBriefPayload): MatterItem[] {
  const items: MatterItem[] = [];
  const flagged = brief.newEvidence.filter((e) => e.flag);
  const plain = brief.newEvidence.filter((e) => !e.flag);
  flagged.forEach((e, i) =>
    items.push({ key: `evf-${i}`, kind: e.type, symbol: e.symbol, text: e.headline, tone: e.tone, t: e.t, url: e.url }),
  );
  brief.signalFlips.forEach((f, i) =>
    items.push({ key: `flip-${i}`, kind: f.kind, symbol: f.symbol, text: f.detail, tone: f.tone }),
  );
  brief.rrgShifts.forEach((s, i) =>
    items.push({ key: `rrg-${i}`, kind: 'rotation', symbol: s.symbol, text: `${s.fromQuadrant} → ${s.toQuadrant}`, tone: s.tone }),
  );
  plain.forEach((e, i) =>
    items.push({ key: `ev-${i}`, kind: e.type, symbol: e.symbol, text: e.headline, tone: e.tone, t: e.t, url: e.url }),
  );
  return items;
}

function formatGeneratedAt(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
}

function RunButton({ generating, onRun, label }: { generating: boolean; onRun: () => void; label: string }) {
  return (
    <button
      onClick={onRun}
      disabled={generating}
      style={{ cursor: generating ? 'default' : 'pointer', border: `1px solid ${MM.borderHi}`, background: MM.accentSoft, color: MM.accent, borderRadius: 9, padding: '6px 12px', font: '600 10px Inter', letterSpacing: '.05em', opacity: generating ? 0.6 : 1, whiteSpace: 'nowrap' }}
    >
      {generating ? '◍ Sweeping…' : label}
    </button>
  );
}

function BriefRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'baseline', borderTop: `1px solid rgba(254,252,244,.05)`, paddingTop: 9 }}>
      <span style={{ flex: '0 0 62px', fontFamily: mono, fontSize: 9, letterSpacing: '.12em', color: MM.dim, textTransform: 'uppercase' }}>{label}</span>
      <div style={{ flex: 1, minWidth: 0 }}>{children}</div>
    </div>
  );
}

export function MorningBrief({
  brief,
  generating,
  onRunNow,
  onOpen,
  regime,
  ledger,
  onExplain,
  calendar,
}: {
  brief: MorningBriefPayload | null;
  generating: boolean;
  onRunNow: () => void;
  onOpen: (symbol: string) => void;
  regime?: Panel<Regime>;
  ledger?: LedgerReport | null;
  onExplain?: () => void;
  calendar?: ReactNode;
}) {
  const [allMatters, setAllMatters] = useState(false);
  const frame = {
    background: `linear-gradient(180deg, rgba(251,148,35,.07), transparent 55%), ${MM.panel}`,
    border: `1px solid rgba(251,148,35,.22)`,
    borderRadius: 14,
    padding: 16,
  };

  if (!brief) {
    return (
      <div style={frame}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
          <span style={{ font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.accent }}>☀ Since you last looked</span>
          <RunButton generating={generating} onRun={onRunNow} label="↻ Run sweep now" />
        </div>
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic', marginTop: 8 }}>
          {generating
            ? 'First pre-market sweep is running — refreshing every symbol, diffing SEC filings and signals…'
            : 'No morning brief yet. The sentinel sweeps pre-market every day and reports what changed overnight.'}
        </div>
      </div>
    );
  }

  const matters = composeMatters(brief);
  const visibleMatters = allMatters ? matters : matters.slice(0, MATTERS_VISIBLE);
  const hiddenCount = matters.length - MATTERS_VISIBLE;
  const regimeCurrent = regime?.data?.current;

  const symbolChip = (symbol: string, key: string, body: ReactNode) => (
    <button
      key={key}
      onClick={() => onOpen(symbol)}
      style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, textAlign: 'left', background: 'rgba(254,252,244,.03)', border: `1px solid ${MM.border}`, borderRadius: 9, padding: '7px 10px', color: MM.textSoft, maxWidth: '100%' }}
    >
      {body}
    </button>
  );

  return (
    <div style={frame}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 10 }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8, font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.accent }}>
          ☀ Since you last looked
          <span style={{ color: MM.dimmer, letterSpacing: '.06em' }}>swept {formatGeneratedAt(brief.generatedAt)}</span>
        </span>
        <RunButton generating={generating} onRun={onRunNow} label="↻ Sweep again" />
      </div>

      <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: 21, color: MM.text, lineHeight: 1.35, marginBottom: 12 }}>
        {brief.headline}
      </div>
      {brief.note && <div style={{ fontSize: 11, color: MM.dim, fontStyle: 'italic', marginBottom: 10 }}>{brief.note}</div>}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {regimeCurrent && (
          <BriefRow label="Regime">
            <span style={{ fontFamily: mono, fontSize: 12, color: REGIME_COLOR[regimeCurrent] ?? MM.textSoft }}>
              {brief.regimeShift ? `${brief.regimeShift.from} → ${brief.regimeShift.to} today` : `${regimeCurrent} — unchanged since last sweep`}
            </span>
            {onExplain && (
              <button onClick={onExplain} style={{ cursor: 'pointer', border: 'none', background: 'transparent', color: MM.dim, font: '600 10px Inter', marginLeft: 8, padding: 0 }}>
                why →
              </button>
            )}
          </BriefRow>
        )}

        <BriefRow label="Matters">
          {matters.length === 0 ? (
            <span style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>
              Nothing thesis-relevant — no new filings, signal flips, or rotation moves.
            </span>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {visibleMatters.map((m) =>
                symbolChip(
                  m.symbol,
                  m.key,
                  <>
                    <span style={{ flex: '0 0 auto', borderRadius: 6, padding: '2px 6px', font: '600 8.5px Inter', letterSpacing: '.08em', textTransform: 'uppercase', background: m.kind === 'Insider' ? MM.accentSoft : 'rgba(254,252,244,.06)', color: m.kind === 'Insider' ? MM.accent : MM.textSoft }}>{m.kind}</span>
                    <span style={{ fontFamily: mono, fontSize: 11, color: MM.text, flex: '0 0 auto' }}>{m.symbol}</span>
                    <span style={{ fontSize: 11.5, lineHeight: 1.4, minWidth: 0, color: toneColor(m.tone) }}>{m.text}</span>
                    {m.url && (
                      <a
                        href={m.url}
                        target="_blank"
                        rel="noreferrer"
                        onClick={(e) => e.stopPropagation()}
                        style={{ marginLeft: 'auto', fontFamily: mono, fontSize: 9.5, color: MM.accent, textDecoration: 'none', flex: '0 0 auto' }}
                      >
                        filing ↗
                      </a>
                    )}
                    {!m.url && evidenceDate(m.t) && <span style={{ marginLeft: 'auto', fontFamily: mono, fontSize: 9.5, color: MM.dimmer, flex: '0 0 auto' }}>{evidenceDate(m.t)}</span>}
                  </>,
                ),
              )}
              {hiddenCount > 0 && (
                <button
                  onClick={() => setAllMatters((v) => !v)}
                  style={{ cursor: 'pointer', border: 'none', background: 'transparent', color: MM.dim, font: '600 10px Inter', textAlign: 'left', padding: '2px 0' }}
                >
                  {allMatters ? '▴ show top 3' : `▾ ${hiddenCount} more`}
                </button>
              )}
            </div>
          )}
        </BriefRow>

        {brief.movers.length > 0 && (
          <BriefRow label={`Movers`}>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
              {brief.movers.map((m, i) => (
                <button
                  key={`mv-${i}`}
                  onClick={() => onOpen(m.symbol)}
                  style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6, background: 'rgba(254,252,244,.03)', border: `1px solid ${MM.border}`, borderRadius: 8, padding: '4px 8px' }}
                >
                  <span style={{ fontFamily: mono, fontSize: 10.5, color: MM.text }}>{m.symbol}</span>
                  <span style={{ fontFamily: mono, fontSize: 10.5, color: toneColor(m.tone) }}>{m.changePct > 0 ? '+' : ''}{m.changePct.toFixed(1)}%</span>
                </button>
              ))}
              <span style={{ fontSize: 9.5, color: MM.dimmer, fontFamily: mono }}>{brief.moversLabel || 'last session'}</span>
            </div>
          </BriefRow>
        )}

        {brief.portfolioNote && (
          <BriefRow label="Book">
            <span style={{ fontSize: 11.5, color: MM.muted }}>{brief.portfolioNote}</span>
          </BriefRow>
        )}

        {calendar && <BriefRow label="Next 7d">{calendar}</BriefRow>}

        {ledger && ledger.totalClaims > 0 && (
          <BriefRow label="Ledger">
            <span style={{ fontFamily: mono, fontSize: 11, color: MM.muted }}>
              {ledger.totalClaims} claims logged · {ledger.pendingHorizons} horizons pending
            </span>
          </BriefRow>
        )}
      </div>
    </div>
  );
}
