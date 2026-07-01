// "Why this read" drill-down for the briefing hero. Shows the data the read was built from and the
// exact logic that produced it — an honest "show your work" view.
// NOTE: the briefing is currently rule-based (core/market/synthesis.py), not a frontier model, so
// this panel surfaces the deterministic logic. When synthesis is upgraded to an LLM, this same panel
// will show the model's captured reasoning instead.

import { useEffect } from 'react';
import type { DashboardPayload, MarketRead } from './types';
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
  marginBottom: 8,
};

export function BriefingReasoning({
  dash,
  read,
  onClose,
}: {
  dash: DashboardPayload;
  read?: MarketRead | null;
  onClose: () => void;
}) {
  const b = dash.briefing.data;
  const logic = regimeLogic(b.breadthPct, b.vix);
  const headline = read?.headline || b.headline;
  const killers = read && read.thesisKillers.length ? read.thesisKillers : dash.contrarian.data;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);
  const ruleBased = !read; // deterministic rules unless a model read exists

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, zIndex: 60, background: 'rgba(0,1,3,.66)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: '9vh', overflowY: 'auto' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ width: 620, maxWidth: '92vw', marginBottom: '6vh', background: '#0c0c0e', border: `1px solid rgba(251,148,35,.18)`, borderRadius: 16, boxShadow: '0 28px 56px rgba(0,0,0,.5)', overflow: 'hidden' }}
      >
        {/* header */}
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, padding: '17px 18px', borderBottom: `1px solid ${MM.border}` }}>
          <div>
            <div style={{ ...sectionLabel, color: MM.accent, marginBottom: 6 }}>Why this read</div>
            <div style={{ fontFamily: "'Cormorant Garamond', serif", fontSize: 22, color: MM.text, lineHeight: 1.15 }}>{headline}</div>
          </div>
          <button onClick={onClose} style={{ cursor: 'pointer', border: `1px solid ${MM.border}`, background: 'transparent', color: MM.muted, borderRadius: 8, padding: '4px 9px', font: '600 10px Inter' }}>esc</button>
        </div>

        <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* the logic */}
          <div>
            <div style={sectionLabel}>How the call was formed</div>
            {read ? (
              <div style={{ fontSize: 12.5, color: MM.textSoft, lineHeight: 1.55 }}>
                Regime read is <span style={{ color: MM.accent, fontWeight: 600 }}>{read.regime}</span>. {read.regimeReasoning}
                {read.caveats && <div style={{ marginTop: 8, fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>Caveats: {read.caveats}</div>}
              </div>
            ) : (
              <div style={{ fontSize: 12.5, color: MM.textSoft, lineHeight: 1.55 }}>
                Regime read is <span style={{ color: MM.accent, fontWeight: 600 }}>{logic.call}</span> because {logic.rule}.
              </div>
            )}
            <div style={{ display: 'flex', gap: 18, marginTop: 10 }}>
              <div><div style={{ fontFamily: mono, fontSize: 16, color: MM.text }}>{b.vix.toFixed(1)}</div><div style={{ ...sectionLabel, marginBottom: 0, marginTop: 2 }}>VIX</div></div>
              <div><div style={{ fontFamily: mono, fontSize: 16, color: MM.up }}>{b.breadthPct.toFixed(0)}%</div><div style={{ ...sectionLabel, marginBottom: 0, marginTop: 2 }}>Breadth</div></div>
            </div>
          </div>

          {/* data snapshot */}
          <div>
            <div style={sectionLabel}>Data it looked at · {dash.asOf}</div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px 18px' }}>
              {dash.macro.data.map((m) => (
                <div key={m.label} style={{ minWidth: 92 }}>
                  <div style={{ font: '600 8.5px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dim }}>{m.label}</div>
                  <div style={{ fontFamily: mono, fontSize: 13, color: MM.text }}>{m.value} <span style={{ fontSize: 10, color: toneColor(m.tone) }}>{m.change}</span></div>
                </div>
              ))}
            </div>
          </div>

          {/* evidence */}
          {dash.evidence.data.length > 0 && (
            <div>
              <div style={sectionLabel}>Evidence considered</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {dash.evidence.data.slice(0, 6).map((e, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 9, fontSize: 11.5, color: MM.textSoft }}>
                    <span style={{ flex: '0 0 auto', borderRadius: 5, padding: '2px 6px', font: '600 8px Inter', letterSpacing: '.06em', textTransform: 'uppercase', background: e.type === 'Insider' ? MM.accentSoft : 'rgba(254,252,244,.06)', color: e.type === 'Insider' ? MM.accent : MM.muted }}>{e.type}</span>
                    <span style={{ fontFamily: mono, fontSize: 11, color: MM.text, width: 46 }}>{e.symbol}</span>
                    <span style={{ flex: 1 }}>{e.headline}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* thesis-killers */}
          {killers.length > 0 && (
            <div>
              <div style={{ ...sectionLabel, color: MM.accent }}>◆ What would make this wrong</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
                {killers.map((c, i) => (
                  <div key={i} style={{ borderLeft: `2px solid rgba(251,148,35,.3)`, paddingLeft: 11 }}>
                    <div style={{ font: '600 8.5px Inter', letterSpacing: '.08em', textTransform: 'uppercase', color: MM.muted, marginBottom: 3 }}>{c.signal}</div>
                    <div style={{ fontSize: 11.5, color: MM.textSoft, lineHeight: 1.5 }}>{c.kill}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {read && (
            <div style={{ borderTop: `1px solid ${MM.border}`, paddingTop: 12, fontSize: 10.5, color: MM.dim, fontStyle: 'italic', lineHeight: 1.5 }}>
              Read generated by {read.model} from the computed facts above — an interpretation with caveats, not a forecast.
              Base rates are quoted from calibration, never invented.
            </div>
          )}
          {ruleBased && (
            <div style={{ borderTop: `1px solid ${MM.border}`, paddingTop: 12, fontSize: 10.5, color: MM.dim, fontStyle: 'italic', lineHeight: 1.5 }}>
              This read is currently computed from the facts above by deterministic rules — not a language model.
              Run “✦ Model read” on the dashboard for a frontier-model interpretation of the same facts.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
