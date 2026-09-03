// Forward Ledger — the model's market calls, logged at read time and scored at horizon
// with pre-registered rules. Calibration ("when it says X, it's right N%") over prediction.
//
// Three layers: the per-kind scorecard, how each kind performed week by week, and every
// claim as an openable row — the reason, the confidence, and each horizon's outcome.

import { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { MM, PanelCard, mono, toneColor } from './marketUi';
import { claimIsScored, hitRate, weeklyOutcomes, type LedgerKind } from './ledgerModel';
import type { LedgerBaseline, LedgerClaim, LedgerReport, Tone } from './types';

const KIND_LABEL: Record<LedgerKind, string> = {
  regime: 'Regime calls',
  lean: 'Ticker leans',
  attention: 'Attention flags',
  screen: 'Screen fires',
};

const VALUE_TONE: Record<string, Tone> = {
  'risk-on': 'up',
  'risk-off': 'down',
  bullish: 'up',
  bearish: 'down',
};

const HORIZONS = ['4w', '8w'] as const;
const ROWS_STEP = 30;

function outcomeGlyph(outcome?: string | null): { text: string; color: string; label: string } {
  if (outcome === 'correct') return { text: '✓', color: MM.up, label: 'correct' };
  if (outcome === 'incorrect') return { text: '✗', color: MM.down, label: 'incorrect' };
  if (outcome === 'push') return { text: '–', color: MM.dim, label: 'neutral' };
  if (outcome === 'unscoreable') return { text: '·', color: MM.dimmer, label: 'unscoreable' };
  return { text: '…', color: MM.dimmer, label: 'pending' };
}

function claimDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function signedPct(value?: number | null): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`;
}

/** One stacked bar per week: correct over incorrect, neutral as a dim cap, pending as an
 *  outline. Height is the number of claims, so a busy week reads busy. */
function WeekStrip({ claims }: { claims: LedgerClaim[] }) {
  const weeks = weeklyOutcomes(claims).slice(-16);
  if (weeks.length === 0) return <span style={{ fontFamily: mono, fontSize: 10, color: MM.dimmer }}>no claims yet</span>;
  const tallest = Math.max(1, ...weeks.map((week) => week.correct + week.incorrect + week.push + week.pending));
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 34 }}>
      {weeks.map((week) => {
        const total = week.correct + week.incorrect + week.push + week.pending;
        const rate = hitRate(week);
        const unit = 34 / tallest;
        const title = `week of ${claimDate(week.weekStart)} · ${week.correct}/${week.correct + week.incorrect} correct${week.push ? ` · ${week.push} neutral` : ''}${week.pending ? ` · ${week.pending} pending` : ''}${rate != null ? ` · ${rate}%` : ''}`;
        return (
          <div key={week.weekStart} title={title} style={{ display: 'flex', flexDirection: 'column-reverse', width: 12, height: total * unit, flex: '0 0 auto' }}>
            <span style={{ height: week.correct * unit, background: MM.up, opacity: 0.85 }} />
            <span style={{ height: week.incorrect * unit, background: MM.down, opacity: 0.85 }} />
            <span style={{ height: week.push * unit, background: MM.dim, opacity: 0.6 }} />
            <span style={{ height: week.pending * unit, border: `1px solid ${MM.dimmer}`, boxSizing: 'border-box' }} />
          </div>
        );
      })}
    </div>
  );
}

/** "vs dart 52% (+15)" — the hit rate only means something next to what chance scored. */
function BaselineLine({ baseline }: { baseline: LedgerBaseline | undefined }) {
  if (!baseline || baseline.pct == null) return <span style={{ fontFamily: mono, fontSize: 9.5, color: MM.dimmer }}>{baseline?.scoredClaims ? 'Baseline unavailable · historical snapshots cannot be matched' : 'Baseline needs scored claims'}</span>;
  const delta = baseline.accuracyPct != null ? baseline.accuracyPct - baseline.pct : null;
  const deltaColor = delta == null ? MM.dim : delta > 0 ? MM.up : delta < 0 ? MM.down : MM.dim;
  return (
    <span style={{ fontFamily: mono, fontSize: 10, color: MM.muted }} title={`${baseline.label}: ${baseline.pct}% vs calls ${baseline.accuracyPct}% on ${baseline.matchedClaims} of ${baseline.scoredClaims} scored claims with matching historical snapshots`}>
      vs {baseline.label.startsWith('dart') ? 'dart' : baseline.label} {baseline.pct}%
      {delta != null && <span style={{ color: deltaColor, marginLeft: 6 }}>{delta > 0 ? '+' : ''}{delta.toFixed(0)}</span>}
      <small style={{ display: 'block', color: MM.dim }}>{baseline.matchedClaims}/{baseline.scoredClaims} matched claims</small>
    </span>
  );
}

function ClaimRow({ claim, onOpen }: { claim: LedgerClaim; onOpen?: (symbol: string) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ borderTop: `1px solid rgba(254,252,244,.05)` }}>
      <button
        type="button"
        className="market-ledger-row"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '7px 4px', border: 0, background: open ? 'rgba(254,252,244,.03)' : 'transparent', color: 'inherit', cursor: 'pointer', textAlign: 'left', font: 'inherit' }}
      >
        <span style={{ color: MM.dimmer, flex: '0 0 auto', display: 'inline-flex' }}>{open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}</span>
        <span style={{ fontFamily: mono, fontSize: 10, color: MM.dimmer, width: 44, flex: '0 0 auto' }}>{claimDate(claim.created_at)}</span>
        <span style={{ flex: '0 0 auto', borderRadius: 3, padding: '2px 6px', font: '600 8px var(--mkt-sans)', letterSpacing: '.08em', textTransform: 'uppercase', background: claim.kind === 'screen' ? 'rgba(105,197,137,.1)' : 'rgba(254,252,244,.05)', color: claim.kind === 'screen' ? MM.up : MM.muted }}>{claim.kind === 'screen' ? claim.signal ?? 'screen' : claim.kind}</span>
        <span
          role={onOpen ? 'link' : undefined}
          onClick={(event) => {
            if (!onOpen) return;
            event.stopPropagation();
            onOpen(claim.target);
          }}
          title={onOpen ? `Open ${claim.target}` : undefined}
          style={{ fontFamily: mono, fontSize: 11.5, fontWeight: 600, color: MM.text, width: 50, flex: '0 0 auto', textDecoration: onOpen ? 'underline dotted rgba(254,252,244,.25)' : 'none', textUnderlineOffset: 3 }}
        >
          {claim.target}
        </span>
        <span style={{ fontFamily: mono, fontSize: 11, color: toneColor(VALUE_TONE[claim.value] || 'flat'), flex: '0 0 auto', width: 64 }}>{claim.value}</span>
        <span style={{ flex: 1, minWidth: 0, fontSize: 11, color: open ? MM.textSoft : MM.dim, whiteSpace: open ? 'normal' : 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.45 }}>{claim.note}</span>
        {HORIZONS.map((horizon) => {
          const slot = claim.horizons?.[horizon];
          const glyph = outcomeGlyph(slot?.resolved_at ? slot.outcome : undefined);
          return (
            <span key={horizon} title={`${horizon}: ${glyph.label}${slot?.return_pct != null ? ` · ${signedPct(slot.return_pct)}` : ''}`} style={{ fontFamily: mono, fontSize: 10.5, color: glyph.color, width: 34, textAlign: 'right', flex: '0 0 auto' }}>
              {horizon} {glyph.text}
            </span>
          );
        })}
      </button>
      {open && (
        <div className="market-ledger-details" style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) auto', gap: 12, padding: '2px 4px 12px 30px' }}>
          <div style={{ fontFamily: mono, fontSize: 10, color: MM.dim, display: 'flex', flexWrap: 'wrap', gap: '4px 14px', alignSelf: 'start' }}>
            <span>logged {new Date(claim.created_at).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}</span>
            <span>model {claim.model}</span>
            {claim.confidence && <span>confidence {claim.confidence}</span>}
          </div>
          <div className="market-ledger-outcomes"><table style={{ borderCollapse: 'collapse', fontFamily: mono, fontSize: 10.5, color: MM.textSoft }}>
            <thead>
              <tr style={{ color: MM.dimmer, font: '600 8px var(--mkt-sans)', letterSpacing: '.08em', textTransform: 'uppercase' }}>
                <th style={{ textAlign: 'left', padding: '0 10px 4px 0' }}>Horizon</th>
                <th style={{ textAlign: 'left', padding: '0 10px 4px 0' }}>Due</th>
                <th style={{ textAlign: 'right', padding: '0 10px 4px 0' }}>Return</th>
                <th style={{ textAlign: 'right', padding: '0 10px 4px 0' }}>vs VOO</th>
                <th style={{ textAlign: 'right', padding: '0 0 4px 0' }}>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {HORIZONS.map((horizon) => {
                const slot = claim.horizons?.[horizon];
                const glyph = outcomeGlyph(slot?.resolved_at ? slot.outcome : undefined);
                return (
                  <tr key={horizon}>
                    <td style={{ padding: '2px 10px 2px 0' }}>{horizon}</td>
                    <td style={{ padding: '2px 10px 2px 0', color: MM.dim }}>{slot ? claimDate(slot.resolved_at ?? slot.due_at) : '—'}{slot && !slot.resolved_at ? ' (due)' : ''}</td>
                    <td style={{ padding: '2px 10px 2px 0', textAlign: 'right', color: slot?.return_pct != null ? toneColor(slot.return_pct > 0 ? 'up' : slot.return_pct < 0 ? 'down' : 'flat') : MM.dimmer }}>{signedPct(slot?.return_pct)}</td>
                    <td style={{ padding: '2px 10px 2px 0', textAlign: 'right', color: slot?.excess_pct != null ? toneColor(slot.excess_pct > 0 ? 'up' : slot.excess_pct < 0 ? 'down' : 'flat') : MM.dimmer }}>{signedPct(slot?.excess_pct)}</td>
                    <td style={{ padding: '2px 0', textAlign: 'right', color: glyph.color }}>{glyph.text} {glyph.label}</td>
                  </tr>
                );
              })}
            </tbody>
          </table></div>
        </div>
      )}
    </div>
  );
}

export function ForwardLedger({ report, loading, onOpen }: { report: LedgerReport | null; loading: boolean; onOpen?: (symbol: string) => void }) {
  const recent = useMemo(() => report?.recent ?? [], [report]);
  const [kind, setKind] = useState<LedgerKind | 'all'>('all');
  const [scoredOnly, setScoredOnly] = useState(false);
  const [limit, setLimit] = useState(ROWS_STEP);

  const rows = recent.filter((claim) => (kind === 'all' || claim.kind === kind) && (!scoredOnly || claimIsScored(claim)));
  const chip = (active: boolean, label: string, onClick: () => void) => (
    <button key={label} type="button" className="mw-chip" aria-pressed={active} onClick={onClick}>{label}</button>
  );

  return (
    <PanelCard
      title="Forward Ledger"
      status={report && report.totalClaims > 0 ? 'live' : 'preview'}
      subtitle="every model read's calls and every screen that fires, logged with prices stamped and scored at 4w/8w against a dart — pre-registered rules, no backfilling"
      right={report ? <span style={{ fontSize: 10, color: MM.dim, whiteSpace: 'nowrap' }}>{report.totalClaims} claims · {report.pendingHorizons} pending</span> : undefined}
    >
      {!report || report.totalClaims === 0 ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>
          {loading ? 'Loading…' : 'No claims yet — from now on, every model read logs its regime call, attention picks, and ticker leans here, and gets scored against what actually happens.'}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: 10 }}>
            {(Object.keys(KIND_LABEL) as LedgerKind[]).map((entry) => {
              const h4 = report.stats[entry]?.['4w'];
              const scored = (h4?.correct ?? 0) + (h4?.incorrect ?? 0);
              const kindClaims = recent.filter((claim) => claim.kind === entry);
              const pending = kindClaims.filter((claim) => !claimIsScored(claim));
              const nextDue = pending.map((claim) => claim.horizons?.['4w']?.due_at).filter(Boolean).sort()[0];
              return (
                <div key={entry} style={{ border: `1px solid ${MM.border}`, borderRadius: 6, padding: '9px 12px', display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <div style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dim }}>{KIND_LABEL[entry]}</div>
                  {scored > 0 ? (
                    <div style={{ fontFamily: mono, fontSize: 15, color: h4!.accuracyPct != null && h4!.accuracyPct >= 50 ? MM.up : MM.down }}>
                      {h4!.correct}/{scored}
                      <span style={{ fontSize: 10.5, color: MM.muted, marginLeft: 6 }}>correct · 4w{h4!.push ? ` · ${h4!.push} neutral` : ''}</span>
                    </div>
                  ) : pending.length > 0 ? (
                    <div style={{ fontFamily: mono, fontSize: 12, color: MM.muted }}>
                      {pending.length} pending
                      {nextDue && <span style={{ fontSize: 10, color: MM.dim, marginLeft: 6 }}>first scores {claimDate(nextDue)}</span>}
                    </div>
                  ) : (
                    <div style={{ fontFamily: mono, fontSize: 12, color: MM.dim }}>no claims yet</div>
                  )}
                  <BaselineLine baseline={report.baseline?.[entry]?.['4w']} />
                  {entry === 'screen' && Object.keys(report.signals ?? {}).length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontFamily: mono, fontSize: 10, color: MM.dim }}>
                      {Object.entries(report.signals).map(([signal, byHorizon]) => {
                        const s4 = byHorizon['4w'];
                        const done = (s4?.correct ?? 0) + (s4?.incorrect ?? 0);
                        const open = kindClaims.filter((claim) => claim.signal === signal && !claimIsScored(claim)).length;
                        return (
                          <span key={signal} style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                            <span style={{ color: MM.muted }}>{signal}</span>
                            <span style={{ color: done ? (s4!.accuracyPct != null && s4!.accuracyPct >= 50 ? MM.up : MM.down) : MM.dimmer }}>
                              {done ? `${s4!.correct}/${done}` : '—'}{open ? ` · ${open} pending` : ''}
                            </span>
                          </span>
                        );
                      })}
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 10 }}>
                    <WeekStrip claims={kindClaims} />
                    <span style={{ font: '500 8px var(--mkt-mono)', color: MM.dimmer, whiteSpace: 'nowrap' }}>by week · 4w</span>
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mw-filters">
            {chip(kind === 'all', 'All', () => setKind('all'))}
            {(Object.keys(KIND_LABEL) as LedgerKind[]).map((entry) => chip(kind === entry, KIND_LABEL[entry], () => setKind(entry)))}
            <span className="tw-sep" style={{ margin: '0 4px' }} />
            {chip(scoredOnly, 'Scored only', () => setScoredOnly((value) => !value))}
            <span style={{ fontFamily: mono, fontSize: 9, color: MM.dimmer, marginLeft: 6 }}>{rows.length} of {recent.length} recent · click a row for the reason and each horizon</span>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {rows.length === 0 && <div style={{ padding: '14px 4px', fontSize: 11, color: MM.dim }}>Nothing matches these filters.</div>}
            {rows.slice(0, limit).map((claim) => <ClaimRow key={claim.claim_id} claim={claim} onOpen={onOpen} />)}
            {rows.length > limit && (
              <button type="button" className="mw-more" style={{ padding: '8px 4px' }} onClick={() => setLimit((value) => value + ROWS_STEP)}>
                show {Math.min(ROWS_STEP, rows.length - limit)} more ↓
              </button>
            )}
          </div>

          <div style={{ fontSize: 10, color: MM.dimmer, fontStyle: 'italic' }}>
            Scoring rules are pre-registered (v{report.rulesVersion.replace('v', '')}): risk-on ≥ +1%, chop ±3%, risk-off ≤ -1% on VOO; leans by forward return sign (neutral = push); attention by ≥5% move or ≥3% vs VOO. Calibration, not forecasts.
          </div>
        </div>
      )}
    </PanelCard>
  );
}
