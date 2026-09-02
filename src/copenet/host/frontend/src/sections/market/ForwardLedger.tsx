// Forward Ledger — the model's market calls, logged at read time and scored at horizon
// with pre-registered rules. Calibration ("when it says X, it's right N%") over prediction.

import { MM, PanelCard, mono, toneColor } from './marketUi';
import type { LedgerClaim, LedgerReport, Tone } from './types';

const KIND_LABEL: Record<LedgerClaim['kind'], string> = {
  regime: 'Regime calls',
  lean: 'Ticker leans',
  attention: 'Attention flags',
};

const VALUE_TONE: Record<string, Tone> = {
  'risk-on': 'up',
  'risk-off': 'down',
  bullish: 'up',
  bearish: 'down',
};

function outcomeGlyph(outcome?: string | null): { text: string; color: string } {
  if (outcome === 'correct') return { text: '✓', color: MM.up };
  if (outcome === 'incorrect') return { text: '✗', color: MM.down };
  if (outcome === 'push') return { text: '–', color: MM.dim };
  if (outcome === 'unscoreable') return { text: '·', color: MM.dimmer };
  return { text: '…', color: MM.dimmer }; // pending
}

function claimDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function ForwardLedger({ report, loading }: { report: LedgerReport | null; loading: boolean }) {
  const recent = report?.recent ?? [];
  return (
    <PanelCard
      title="Forward Ledger"
      status={report && report.totalClaims > 0 ? 'live' : 'preview'}
      subtitle="every model read's calls, logged with prices stamped and scored at 4w/8w — pre-registered rules, no backfilling"
      right={
        report ? (
          <span style={{ fontSize: 10, color: MM.dim, whiteSpace: 'nowrap' }}>
            {report.totalClaims} claims · {report.pendingHorizons} pending
          </span>
        ) : undefined
      }
    >
      {!report || report.totalClaims === 0 ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>
          {loading ? 'Loading…' : 'No claims yet — from now on, every model read logs its regime call, attention picks, and ticker leans here, and gets scored against what actually happens.'}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
            {(Object.keys(KIND_LABEL) as LedgerClaim['kind'][]).map((kind) => {
              const h4 = report.stats[kind]?.['4w'];
              const scored = (h4?.correct ?? 0) + (h4?.incorrect ?? 0);
              const kindClaims = recent.filter((c) => c.kind === kind);
              const pending = kindClaims.filter((c) => !c.horizons?.['4w']?.resolved_at);
              const nextDue = pending
                .map((c) => c.horizons?.['4w']?.due_at)
                .filter(Boolean)
                .sort()[0];
              return (
                <div key={kind} style={{ flex: 1, minWidth: 150, border: `1px solid ${MM.border}`, borderRadius: 10, padding: '9px 12px' }}>
                  <div style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dim, marginBottom: 4 }}>{KIND_LABEL[kind]}</div>
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
                </div>
              );
            })}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', maxHeight: 220, overflowY: 'auto', paddingRight: 4 }}>
            {recent.slice(0, 12).map((claim) => (
              <div key={claim.claim_id} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0', borderTop: `1px solid rgba(254,252,244,.05)` }}>
                <span style={{ fontFamily: mono, fontSize: 10, color: MM.dimmer, width: 44, flex: '0 0 auto' }}>{claimDate(claim.created_at)}</span>
                <span style={{ flex: '0 0 auto', borderRadius: 6, padding: '2px 7px', font: '600 8px var(--mkt-sans)', letterSpacing: '.08em', textTransform: 'uppercase', background: 'rgba(254,252,244,.05)', color: MM.muted }}>{claim.kind}</span>
                <span style={{ fontFamily: mono, fontSize: 11.5, fontWeight: 600, color: MM.text, width: 46, flex: '0 0 auto' }}>{claim.target}</span>
                <span style={{ fontFamily: mono, fontSize: 11, color: toneColor(VALUE_TONE[claim.value] || 'flat'), flex: '0 0 auto' }}>{claim.value}</span>
                <span style={{ flex: 1, fontSize: 10.5, color: MM.dim, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{claim.note}</span>
                {(['4w', '8w'] as const).map((h) => {
                  const slot = claim.horizons?.[h];
                  const glyph = outcomeGlyph(slot?.resolved_at ? slot.outcome : undefined);
                  return (
                    <span key={h} title={slot?.return_pct != null ? `${h}: ${slot.return_pct > 0 ? '+' : ''}${slot.return_pct}%` : `${h}: pending`} style={{ fontFamily: mono, fontSize: 10.5, color: glyph.color, width: 34, textAlign: 'right', flex: '0 0 auto' }}>
                      {h} {glyph.text}
                    </span>
                  );
                })}
              </div>
            ))}
          </div>
          <div style={{ fontSize: 10, color: MM.dimmer, fontStyle: 'italic' }}>
            Scoring rules are pre-registered (v{report.rulesVersion.replace('v', '')}): risk-on ≥ +1%, chop ±3%, risk-off ≤ -1% on VOO; leans by forward return sign (neutral = push); attention by ≥5% move or ≥3% vs VOO. Calibration, not forecasts.
          </div>
        </div>
      )}
    </PanelCard>
  );
}
