import { MM, PanelCard, mono, toneColor } from './marketUi';
import type { TickerDetailPayload, Tone } from './types';

function formatBigNumber(value: number, prefix = ''): string {
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${prefix}${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${prefix}${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${prefix}${(value / 1e6).toFixed(1)}M`;
  return `${prefix}${Math.round(value).toLocaleString()}`;
}

function statRows(stats?: TickerDetailPayload['stats']): { key: string; value: string; tone: Tone }[] {
  if (!stats) return [];
  const rows: { key: string; value: string; tone: Tone }[] = [];
  if (stats.marketCap != null) rows.push({ key: 'Market cap', value: formatBigNumber(stats.marketCap, '$'), tone: 'flat' });
  if (stats.yearHigh != null && stats.yearLow != null) rows.push({ key: '52-week range', value: `$${stats.yearLow.toFixed(2)} – $${stats.yearHigh.toFixed(2)}`, tone: 'flat' });
  if (stats.avgVolume3m != null) rows.push({ key: 'Average volume · 3m', value: formatBigNumber(stats.avgVolume3m), tone: 'flat' });
  return rows;
}

export function TickerSignalPanel({ detail }: { detail: TickerDetailPayload }) {
  const rows = [...statRows(detail.stats), ...detail.signals];
  return (
    <div className="ticker-analysis-grid">
      {detail.insight?.softBottoming && (
        <section style={{ background: `linear-gradient(180deg, rgba(105,197,137,.07), transparent 52%), ${MM.panel}`, border: `1px solid rgba(105,197,137,.25)`, borderRadius: 8, padding: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 }}>
            <h3 style={{ margin: 0, font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.up }}>Soft-bottoming setup</h3>
            <span style={{ fontFamily: mono, fontSize: 12, color: MM.up }}>score {detail.insight.score.toFixed(2)}</span>
          </div>
          <p style={{ margin: '0 0 11px', fontSize: 11.5, color: MM.textSoft, lineHeight: 1.5 }}>
            {detail.insight.baseRate ? `${detail.insight.baseRate.headline}. ` : 'Base rate is still calibrating. '}
            <span style={{ color: MM.dim }}>This is a measured setup, not a forecast.</span>
          </p>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '5px 12px' }}>
            {detail.insight.components.map((component) => (
              <span key={component.label} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10.5, color: component.met ? MM.textSoft : MM.dim }}>
                <span style={{ color: component.met ? MM.up : MM.dimmer, fontFamily: mono }}>{component.met ? '✓' : '·'}</span>{component.label}
              </span>
            ))}
          </div>
        </section>
      )}

      <PanelCard title="Deterministic readout" status="live">
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {rows.map((row, index) => (
            <div key={`${row.key}-${index}`} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: '7px 0', borderTop: index ? `1px solid rgba(254,252,244,.05)` : 'none' }}>
              <span style={{ fontSize: 11.5, color: MM.muted }}>{row.key}</span>
              <span style={{ fontFamily: mono, fontSize: 11.5, color: toneColor(row.tone), textAlign: 'right' }}>{row.value}</span>
            </div>
          ))}
        </div>
      </PanelCard>

      <section style={{ background: `linear-gradient(180deg, rgba(251,148,35,.05), transparent 50%), ${MM.panel}`, border: `1px solid rgba(251,148,35,.16)`, borderRadius: 8, padding: 12 }}>
        <h3 style={{ margin: '0 0 9px', font: '600 9.5px Inter', letterSpacing: '.14em', textTransform: 'uppercase', color: MM.accent }}>What would make this wrong</h3>
        <p style={{ margin: 0, fontSize: 12, color: MM.textSoft, lineHeight: 1.55 }}>{detail.kill}</p>
      </section>
    </div>
  );
}
