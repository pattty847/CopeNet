// The market briefing — the model's read presented as something you actually sit and read.
//
// This used to be a 620px "show your work" modal, and the model's best writing was scattered
// across the dashboard as tooltips and panel captions: `regimeReasoning` in particular was a
// native title= attribute, which meant hovering on desktop and no access at all on a phone.
// The content was never the problem; the presentation was. So this is a full-screen reading
// view that runs the read in narrative order — what happened, how it squares with the prior
// sessions, the regime call, rotation, what to watch, what would prove it wrong — and keeps
// the forensic material (macro strip, evidence, the deterministic rule) below the fold as an
// appendix rather than as the main event.

import { useEffect } from 'react';
import type { DashboardPayload, MarketRead, MarketSession } from './types';
import { MM, mono, toneColor } from './marketUi';

function regimeLogic(breadthPct: number, vix: number): { call: string; rule: string } {
  if (breadthPct >= 55 && vix < 20) {
    return { call: 'risk-on', rule: `breadth ${breadthPct.toFixed(0)}% ≥ 55% and VIX ${vix.toFixed(1)} < 20` };
  }
  if (breadthPct < 40 || vix >= 25) {
    return { call: 'risk-off', rule: `breadth ${breadthPct.toFixed(0)}% < 40% or VIX ${vix.toFixed(1)} ≥ 25` };
  }
  return { call: 'chop', rule: `breadth ${breadthPct.toFixed(0)}% and VIX ${vix.toFixed(1)} sit between the risk-on and risk-off thresholds` };
}

const sectionLabel = {
  font: '600 9px Inter',
  letterSpacing: '.14em',
  textTransform: 'uppercase' as const,
  color: MM.muted,
  marginBottom: 10,
};

/** Reading measure, not dashboard density: ~68 characters a line at this size. */
const prose = {
  fontSize: 15,
  lineHeight: 1.68,
  color: MM.textSoft,
  margin: 0,
  maxWidth: '34em',
};

function Section({ label, accent, children }: { label: string; accent?: boolean; children: React.ReactNode }) {
  return (
    <section>
      <div style={{ ...sectionLabel, color: accent ? MM.accent : MM.muted }}>{label}</div>
      {children}
    </section>
  );
}

function editionLabel(generatedAt?: string): string {
  if (!generatedAt) return '';
  const d = new Date(generatedAt);
  if (Number.isNaN(d.getTime())) return '';
  return d.toLocaleString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

export function BriefingReasoning({
  dash,
  read,
  sessions = [],
  onClose,
}: {
  dash: DashboardPayload;
  read?: MarketRead | null;
  sessions?: MarketSession[];
  onClose: () => void;
}) {
  const b = dash.briefing.data;
  const logic = regimeLogic(b.breadthPct, b.vix);
  const headline = read?.headline || b.headline;
  const killers = read && read.thesisKillers.length ? read.thesisKillers : dash.contrarian.data;
  const ruleBased = !read; // deterministic rules unless a model read exists

  // Today is the story being told, not part of the trail behind it.
  const priorSessions = sessions.filter((s) => s.date !== String(read?.generatedAt || '').slice(0, 10));

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    // A full-screen reader should not leave the dashboard scrolling underneath it.
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('keydown', onKey);
      document.body.style.overflow = previousOverflow;
    };
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Market briefing"
      style={{ position: 'fixed', inset: 0, zIndex: 60, background: '#0a0a0c', overflowY: 'auto', WebkitOverflowScrolling: 'touch' }}
    >
      {/* Sticky bar: the way out stays reachable however far down you read. */}
      <div
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 12,
          padding: '14px 20px',
          background: 'rgba(10,10,12,.92)',
          backdropFilter: 'blur(8px)',
          borderBottom: `1px solid ${MM.border}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12, minWidth: 0 }}>
          <span style={{ ...sectionLabel, color: MM.accent, marginBottom: 0 }}>Market Briefing</span>
          {editionLabel(read?.generatedAt) && (
            <span style={{ fontSize: 11.5, color: MM.dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {editionLabel(read?.generatedAt)}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          aria-label="Close briefing"
          style={{ cursor: 'pointer', border: `1px solid ${MM.border}`, background: 'transparent', color: MM.muted, borderRadius: 8, padding: '6px 12px', font: '600 10px Inter', minHeight: 32, flex: '0 0 auto' }}
        >
          esc
        </button>
      </div>

      <article style={{ maxWidth: 760, margin: '0 auto', padding: '38px 20px 96px', display: 'flex', flexDirection: 'column', gap: 34 }}>
        <header>
          <h1 style={{ margin: '0 0 18px', fontFamily: "'Cormorant Garamond', serif", fontWeight: 600, fontSize: 42, lineHeight: 1.1, letterSpacing: '-.01em', color: MM.text }}>
            {headline}
          </h1>
          {(read?.summary || b.summary) && <p style={{ ...prose, fontSize: 16.5, color: MM.muted }}>{read?.summary || b.summary}</p>}
        </header>

        {/* The day-over-day thread, given top billing: the point of reading these in sequence. */}
        {read?.continuity && (
          <Section label="Since the last read" accent>
            <p style={prose}>{read.continuity}</p>
          </Section>
        )}

        <Section label="The regime call">
          <p style={prose}>
            The tape reads{' '}
            <span style={{ color: MM.accent, fontWeight: 600 }}>{read ? read.regime : logic.call}</span>
            {read ? '. ' : ` because ${logic.rule}.`}
            {read?.regimeReasoning}
          </p>
          <div style={{ display: 'flex', gap: 26, marginTop: 16 }}>
            <div>
              <div style={{ fontFamily: mono, fontSize: 20, color: MM.text }}>{b.vix.toFixed(1)}</div>
              <div style={{ ...sectionLabel, marginBottom: 0, marginTop: 3 }}>VIX</div>
            </div>
            <div>
              <div style={{ fontFamily: mono, fontSize: 20, color: MM.up }}>{b.breadthPct.toFixed(0)}%</div>
              <div style={{ ...sectionLabel, marginBottom: 0, marginTop: 3 }}>Breadth</div>
            </div>
          </div>
        </Section>

        {read?.rotationRead && (
          <Section label="Where money is moving">
            <p style={prose}>{read.rotationRead}</p>
          </Section>
        )}

        {read && read.attention.length > 0 && (
          <Section label="What deserves attention">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {read.attention.map((a, i) => (
                <div key={i} style={{ borderLeft: `2px solid ${MM.accentSoft}`, paddingLeft: 14 }}>
                  <div style={{ display: 'flex', alignItems: 'baseline', gap: 9, marginBottom: 4 }}>
                    <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 600, color: MM.text }}>{a.symbol}</span>
                    <span style={{ font: '600 8.5px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dim }}>{a.kind}</span>
                  </div>
                  <p style={{ ...prose, fontSize: 13.5 }}>{a.why}</p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {read?.speculativeComment && (
          <Section label="The speculative lane">
            <p style={prose}>{read.speculativeComment}</p>
          </Section>
        )}

        {killers.length > 0 && (
          <Section label="◆ What would make this wrong" accent>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {killers.map((c, i) => (
                <div key={i} style={{ borderLeft: `2px solid rgba(251,148,35,.3)`, paddingLeft: 14 }}>
                  <div style={{ font: '600 8.5px Inter', letterSpacing: '.08em', textTransform: 'uppercase', color: MM.muted, marginBottom: 4 }}>{c.signal}</div>
                  <p style={{ ...prose, fontSize: 13.5 }}>{c.kill}</p>
                </div>
              ))}
            </div>
          </Section>
        )}

        {read?.caveats && (
          <Section label="Caveats">
            <p style={{ ...prose, fontSize: 13.5, color: MM.dim, fontStyle: 'italic' }}>{read.caveats}</p>
          </Section>
        )}

        {priorSessions.length > 0 && (
          <Section label="The sessions before this">
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {priorSessions.map((s) => (
                <div key={s.date} style={{ display: 'flex', gap: 14, padding: '11px 0', borderTop: `1px solid rgba(254,252,244,.05)` }}>
                  <span style={{ fontFamily: mono, fontSize: 11, color: MM.dim, flex: '0 0 76px' }}>{s.date}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, color: MM.textSoft, lineHeight: 1.5 }}>{s.headline}</div>
                    {s.rrgShifts.length > 0 && (
                      <div style={{ fontSize: 11, color: MM.dim, marginTop: 3 }}>
                        {s.rrgShifts.slice(0, 4).map((r) => `${r.symbol} ${r.fromQuadrant}→${r.toQuadrant}`).join(' · ')}
                      </div>
                    )}
                  </div>
                  {s.regime && (
                    <span style={{ font: '600 9px Inter', letterSpacing: '.08em', textTransform: 'uppercase', color: MM.muted, flex: '0 0 auto' }}>{s.regime}</span>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Appendix: the forensic material, deliberately after the read rather than instead of it. */}
        <Section label={`The facts behind it · ${dash.asOf}`}>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '12px 22px', marginBottom: 18 }}>
            {dash.macro.data.map((m) => (
              <div key={m.label} style={{ minWidth: 96 }}>
                <div style={{ font: '600 8.5px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dim }}>{m.label}</div>
                <div style={{ fontFamily: mono, fontSize: 13.5, color: MM.text }}>
                  {m.value} <span style={{ fontSize: 10, color: toneColor(m.tone) }}>{m.change}</span>
                </div>
              </div>
            ))}
          </div>
          {dash.evidence.data.length > 0 && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {dash.evidence.data.slice(0, 8).map((e, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 12, color: MM.textSoft }}>
                  <span style={{ flex: '0 0 auto', borderRadius: 5, padding: '2px 6px', font: '600 8px Inter', letterSpacing: '.06em', textTransform: 'uppercase', background: e.type === 'Insider' ? MM.accentSoft : 'rgba(254,252,244,.06)', color: e.type === 'Insider' ? MM.accent : MM.muted }}>{e.type}</span>
                  <span style={{ fontFamily: mono, fontSize: 11, color: MM.text, width: 48, flex: '0 0 48px' }}>{e.symbol}</span>
                  <span style={{ flex: 1, minWidth: 0 }}>{e.headline}</span>
                </div>
              ))}
            </div>
          )}
        </Section>

        <footer style={{ borderTop: `1px solid ${MM.border}`, paddingTop: 16, fontSize: 11, color: MM.dim, fontStyle: 'italic', lineHeight: 1.6 }}>
          {read ? (
            <>
              Read generated by {read.model} from the computed facts above — an interpretation with caveats, not a
              forecast. Base rates are quoted from calibration, never invented.
            </>
          ) : null}
          {ruleBased ? (
            <>
              This read is currently computed from the facts above by deterministic rules — not a language model. Run
              “✦ Model read” on the dashboard for a frontier-model interpretation of the same facts.
            </>
          ) : null}
        </footer>
      </article>
    </div>
  );
}
