import { lazy, Suspense, useState } from 'react';
import { EvidenceFlagBadge, EvidenceToneGlyph, MM, evidenceDate, evidenceTypeBg, evidenceTypeColor, mono, toneColor } from './marketUi';
import { sortEvidenceNewestFirst } from './marketEvidence';
import { evidenceDay } from './secActivity';
import { SEC_DEPTHS, type TickerEvidenceState } from './useMarketMonitorData';
import type { InsiderNetWindow, Tone } from './types';

const SecActivityChart = lazy(() => import('./SecActivityChart').then((module) => ({ default: module.SecActivityChart })));

function signTone(value: number): Tone {
  return value > 0 ? 'up' : value < 0 ? 'down' : 'flat';
}

function compactNumber(value: number, unit: 'shares' | 'money'): string {
  const abs = Math.abs(value);
  const sign = value > 0 ? '+' : value < 0 ? '-' : '';
  const prefix = unit === 'money' ? '$' : '';
  const suffix = unit === 'shares' ? ' sh' : '';
  if (abs >= 1e9) return `${sign}${prefix}${(abs / 1e9).toFixed(1)}B${suffix}`;
  if (abs >= 1e6) return `${sign}${prefix}${(abs / 1e6).toFixed(1)}M${suffix}`;
  if (abs >= 1e3) return `${sign}${prefix}${(abs / 1e3).toFixed(0)}K${suffix}`;
  return `${sign}${prefix}${abs.toLocaleString()}${suffix}`;
}

function InsiderWindow({ window }: { window: InsiderNetWindow }) {
  const shareTone = signTone(window.netShares);
  const valueTone = window.netValue == null ? shareTone : signTone(window.netValue);
  return (
    <div style={{ flex: 1, minWidth: 145, border: `1px solid ${valueTone === 'up' ? 'rgba(105,197,137,.25)' : valueTone === 'down' ? 'rgba(217,109,95,.25)' : MM.border}`, background: valueTone === 'up' ? 'rgba(105,197,137,.05)' : valueTone === 'down' ? 'rgba(217,109,95,.05)' : 'transparent', borderRadius: 9, padding: '8px 10px' }}>
      <div style={{ font: '600 8px Inter', letterSpacing: '.1em', textTransform: 'uppercase', color: MM.dim, marginBottom: 3 }}>{window.days}d insider net</div>
      <div style={{ fontFamily: mono, fontSize: 12, color: toneColor(valueTone) }}>{window.netValue != null ? compactNumber(window.netValue, 'money') : compactNumber(window.netShares, 'shares')}</div>
      {window.netValue != null && <div style={{ fontFamily: mono, fontSize: 9.5, color: toneColor(shareTone), marginTop: 2 }}>{compactNumber(window.netShares, 'shares')}</div>}
      <div style={{ fontFamily: mono, fontSize: 9.5, color: MM.dim, marginTop: 2 }}>{window.buys} buys · {window.sells} sells · {window.openMarketBuys ?? 0} open-market</div>
    </div>
  );
}

export function TickerEvidencePanel({ state, active }: { state: TickerEvidenceState; active: boolean }) {
  const [showMethod, setShowMethod] = useState(false);
  const [selectedDay, setSelectedDay] = useState<string | null>(null);
  const evidence = sortEvidenceNewestFirst(state.payload?.evidence ?? []);
  const effectiveSelectedDay = selectedDay && evidence.some((item) => evidenceDay(item) === selectedDay) ? selectedDay : null;
  const visibleEvidence = effectiveSelectedDay ? evidence.filter((item) => evidenceDay(item) === effectiveSelectedDay) : evidence;
  const insiderWindows = Object.values(state.payload?.insiderNet ?? {}).sort((a, b) => a.days - b.days);

  const actions = (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
          <div role="group" aria-label="SEC history depth" style={{ display: 'flex', gap: 3, background: '#050506', border: `1px solid ${MM.border}`, borderRadius: 8, padding: 3 }}>
            {SEC_DEPTHS.map((depth) => (
              <button key={depth.days} type="button" onClick={() => state.setDepthDays(depth.days)} aria-pressed={state.depthDays === depth.days} style={{ cursor: 'pointer', border: 'none', borderRadius: 5, padding: '4px 8px', font: '600 9px Inter', background: state.depthDays === depth.days ? MM.accent : 'transparent', color: state.depthDays === depth.days ? '#1a1205' : MM.muted }}>{depth.label}</button>
            ))}
          </div>
          <button type="button" onClick={() => void state.refresh()} disabled={state.refreshing} style={{ cursor: state.refreshing ? 'default' : 'pointer', border: `1px solid rgba(251,148,35,.3)`, background: 'transparent', color: MM.accent, borderRadius: 8, padding: '5px 10px', font: '600 9px Inter', opacity: state.refreshing ? 0.6 : 1 }}>
            {state.refreshing ? 'Checking…' : 'Check SEC now'}
          </button>
    </div>
  );
  const body = (
    <>
      {state.error && <div role="alert" style={{ fontSize: 11, color: MM.down, marginBottom: 8 }}>{state.error}</div>}
      {(state.payload?.warnings ?? []).map((warning) => <div key={warning} role="status" style={{ fontSize: 10.5, color: MM.accent, marginBottom: 6 }}>{warning}</div>)}
      {active && evidence.length > 0 ? (
        <Suspense fallback={<div className="sec-activity-skeleton" aria-label="Loading SEC activity chart"><span /><span /><span /><span /></div>}>
          <SecActivityChart evidence={evidence} selectedDay={effectiveSelectedDay} onSelectDay={setSelectedDay} />
        </Suspense>
      ) : null}
      {insiderWindows.length > 0 && (
        <>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>{insiderWindows.map((window) => <InsiderWindow key={window.days} window={window} />)}</div>
          <button type="button" onClick={() => setShowMethod((value) => !value)} aria-expanded={showMethod} style={{ border: 'none', background: 'transparent', color: MM.dim, padding: 0, marginBottom: 9, cursor: 'pointer', font: '500 10px Inter' }}>
            {showMethod ? 'Hide insider-flow method' : 'How insider flow is classified'}
          </button>
          {showMethod && <p style={{ margin: '0 0 10px', color: MM.dim, fontSize: 10.5, lineHeight: 1.5 }}>Share counts include grants, vesting, and exercises. Dollar flow reflects cash spent or received and determines the tile tone; open-market purchases are called out separately.</p>}
        </>
      )}
      {state.loading && evidence.length === 0 ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>Loading cached SEC evidence…</div>
      ) : evidence.length === 0 ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>No activity found in this window.</div>
      ) : (
        <>
          {effectiveSelectedDay ? <div className="sec-evidence-filter"><span>Showing {visibleEvidence.length} {visibleEvidence.length === 1 ? 'event' : 'events'} from {new Intl.DateTimeFormat(undefined, { month: 'long', day: 'numeric', year: 'numeric' }).format(new Date(`${effectiveSelectedDay}T00:00:00Z`))}</span><button type="button" onClick={() => setSelectedDay(null)}>Clear filter</button></div> : null}
          <div className="ticker-evidence-list is-embedded" style={{ display: 'flex', flexDirection: 'column', paddingRight: 4 }}>
          {visibleEvidence.map((item, index) => {
            const body = (
              <>
                <span style={{ flex: '0 0 auto', borderRadius: 6, padding: '3px 7px', font: '600 8.5px Inter', letterSpacing: '.08em', textTransform: 'uppercase', background: evidenceTypeBg(item.type), color: evidenceTypeColor(item.type) }}>{item.type}</span>
                <span style={{ flex: 1, minWidth: 0, fontSize: 12, color: MM.textSoft, lineHeight: 1.4, display: 'inline-flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}><EvidenceToneGlyph tone={item.tone} />{item.headline}<EvidenceFlagBadge flag={item.flag} /></span>
                <span style={{ flex: '0 0 auto', fontSize: 10, color: MM.dim, whiteSpace: 'nowrap', textAlign: 'right' }}>{item.source}<span style={{ display: 'block', color: MM.dimmer }}>{evidenceDate(item.t)}</span></span>
              </>
            );
            const style = { display: 'flex', alignItems: 'center', gap: 10, padding: '9px 0', borderTop: index ? `1px solid rgba(254,252,244,.05)` : 'none', textAlign: 'left' as const };
            return item.url
              ? <a key={`${item.type}-${item.t}-${item.headline}`} href={item.url} target="_blank" rel="noreferrer" style={{ ...style, textDecoration: 'none' }}>{body}</a>
              : <div key={`${item.type}-${item.t}-${item.headline}`} style={style}>{body}</div>;
          })}
          </div>
        </>
      )}
    </>
  );
  return (
    <section className="ticker-evidence-panel is-embedded">
      <header className="ticker-embedded-panel-header">
        <div><h3>SEC & event investigation</h3><p>{state.payload?.asOf ? `Cached as of ${new Date(state.payload.asOf).toLocaleString()}` : 'Form 4, Form 144, and 8-K activity'}</p></div>
        {actions}
      </header>
      {body}
    </section>
  );
}
