// "Since you last looked" — the overnight sentinel's morning delta brief.
// Renders only deltas (new filings, signal flips, rotation moves, movers); the standing
// picture lives in the panels below. Honest empty state until the first sweep lands.

import type { ReactNode } from 'react';
import { MM, mono, toneColor } from './marketUi';
import type { MorningBriefPayload } from './types';

const SECTION_LABEL = { font: '600 9px Inter', letterSpacing: '.12em', textTransform: 'uppercase' as const, color: MM.dim, marginBottom: 6 };

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

export function MorningBrief({
  brief,
  generating,
  onRunNow,
  onOpen,
}: {
  brief: MorningBriefPayload | null;
  generating: boolean;
  onRunNow: () => void;
  onOpen: (symbol: string) => void;
}) {
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
            : 'No morning brief yet. The sentinel sweeps pre-market every day at 7:00 AM and reports what changed overnight.'}
        </div>
      </div>
    );
  }

  const hasDeltas =
    brief.newEvidence.length > 0 || brief.signalFlips.length > 0 || brief.rrgShifts.length > 0 || Boolean(brief.regimeShift);

  const symbolChip = (symbol: string, key: string, body: ReactNode) => (
    <button
      key={key}
      onClick={() => onOpen(symbol)}
      style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, textAlign: 'left', background: 'rgba(254,252,244,.03)', border: `1px solid ${MM.border}`, borderRadius: 9, padding: '7px 10px', color: MM.textSoft }}
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

      <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: 21, color: MM.text, lineHeight: 1.35, marginBottom: hasDeltas || brief.movers.length ? 12 : 0 }}>
        {brief.headline}
      </div>
      {brief.note && <div style={{ fontSize: 11, color: MM.dim, fontStyle: 'italic', marginBottom: 10 }}>{brief.note}</div>}

      <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap' }}>
        {brief.newEvidence.length > 0 && (
          <div style={{ flex: 1.4, minWidth: 280 }}>
            <div style={SECTION_LABEL}>New SEC activity</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {brief.newEvidence.map((e, i) =>
                symbolChip(
                  e.symbol,
                  `ev-${i}`,
                  <>
                    <span style={{ flex: '0 0 auto', borderRadius: 6, padding: '2px 6px', font: '600 8.5px Inter', letterSpacing: '.08em', textTransform: 'uppercase', background: e.type === 'Insider' ? MM.accentSoft : 'rgba(254,252,244,.06)', color: e.type === 'Insider' ? MM.accent : MM.textSoft }}>{e.type}</span>
                    <span style={{ fontFamily: mono, fontSize: 11, color: MM.text, flex: '0 0 auto' }}>{e.symbol}</span>
                    <span style={{ fontSize: 11.5, lineHeight: 1.4, minWidth: 0 }}>{e.headline}</span>
                  </>,
                ),
              )}
            </div>
          </div>
        )}

        {(brief.signalFlips.length > 0 || brief.rrgShifts.length > 0 || brief.regimeShift) && (
          <div style={{ flex: 1, minWidth: 240 }}>
            <div style={SECTION_LABEL}>Signal & rotation changes</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {brief.regimeShift && (
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '7px 10px', borderRadius: 9, border: `1px solid rgba(251,148,35,.3)`, background: 'rgba(251,148,35,.06)' }}>
                  <span style={{ font: '600 8.5px Inter', letterSpacing: '.08em', textTransform: 'uppercase', color: MM.accent }}>Regime</span>
                  <span style={{ fontFamily: mono, fontSize: 11.5, color: MM.text }}>{brief.regimeShift.from} → {brief.regimeShift.to}</span>
                </div>
              )}
              {brief.rrgShifts.map((s, i) =>
                symbolChip(
                  s.symbol,
                  `rrg-${i}`,
                  <>
                    <span style={{ fontFamily: mono, fontSize: 11, color: MM.text, flex: '0 0 auto' }}>{s.symbol}</span>
                    <span style={{ fontSize: 11.5, color: toneColor(s.tone) }}>{s.fromQuadrant} → {s.toQuadrant}</span>
                  </>,
                ),
              )}
              {brief.signalFlips.map((f, i) =>
                symbolChip(
                  f.symbol,
                  `flip-${i}`,
                  <>
                    <span style={{ fontFamily: mono, fontSize: 11, color: MM.text, flex: '0 0 auto' }}>{f.symbol}</span>
                    <span style={{ fontSize: 11.5, color: toneColor(f.tone) }}>{f.detail}</span>
                  </>,
                ),
              )}
            </div>
          </div>
        )}

        {brief.movers.length > 0 && (
          <div style={{ flex: 1, minWidth: 220 }}>
            <div style={SECTION_LABEL}>Movers · {brief.moversLabel || 'last session'}</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {brief.movers.map((m, i) =>
                symbolChip(
                  m.symbol,
                  `mv-${i}`,
                  <>
                    <span style={{ fontFamily: mono, fontSize: 11, color: MM.text, flex: '0 0 auto' }}>{m.symbol}</span>
                    <span style={{ fontFamily: mono, fontSize: 11.5, color: toneColor(m.tone) }}>{m.changePct > 0 ? '+' : ''}{m.changePct.toFixed(1)}%</span>
                    <span style={{ fontSize: 10.5, color: MM.dim, marginLeft: 'auto' }}>{m.last}</span>
                  </>,
                ),
              )}
            </div>
            {brief.portfolioNote && (
              <div style={{ fontSize: 11, color: MM.muted, marginTop: 8, borderTop: `1px solid rgba(254,252,244,.05)`, paddingTop: 8 }}>{brief.portfolioNote}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
