import { MM, mono, toneColor } from './marketUi';
import type { EvidenceItem, TickerDetailPayload, Tone } from './types';

function signedPercent(value?: number | null, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

function tone(value?: number | null): Tone {
  return value == null || value === 0 ? 'flat' : value > 0 ? 'up' : 'down';
}

function formatBigNumber(value: number, prefix = ''): string {
  const abs = Math.abs(value);
  if (abs >= 1e12) return `${prefix}${(value / 1e12).toFixed(2)}T`;
  if (abs >= 1e9) return `${prefix}${(value / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${prefix}${(value / 1e6).toFixed(1)}M`;
  return `${prefix}${Math.round(value).toLocaleString()}`;
}

export function latestMaterialEvidence(items: EvidenceItem[]): EvidenceItem | null {
  return [...items]
    .filter((item) => item.flag || item.type === 'Insider' || item.type === '8-K')
    .sort((a, b) => (b.t ?? 0) - (a.t ?? 0))[0] ?? null;
}

export function TickerOverviewPanel({ detail, evidence }: { detail: TickerDetailPayload; evidence: EvidenceItem[] }) {
  const intelligence = detail.intelligence;
  const position = intelligence?.portfolio;
  const rows: Array<{ label: string; value: string; valueTone?: Tone }> = [];
  if (detail.stats?.marketCap != null) rows.push({ label: 'Market cap', value: formatBigNumber(detail.stats.marketCap, '$') });
  if (detail.stats?.yearHigh != null && detail.stats?.yearLow != null) rows.push({ label: '52-week range', value: `$${detail.stats.yearLow.toFixed(2)} – $${detail.stats.yearHigh.toFixed(2)}` });
  if (detail.stats?.avgVolume3m != null) rows.push({ label: 'Average volume · 3m', value: formatBigNumber(detail.stats.avgVolume3m) });
  rows.push(...detail.signals.map((row) => ({ label: row.key, value: row.value, valueTone: row.tone })));

  return (
    <div className="ticker-overview-panel">
      <div className="ticker-overview-columns">
        <section className="ticker-research-section">
          <h3>Measured state · fixed horizons</h3>
          <div className="ticker-metric-table">
            {rows.map((row, index) => (
              <Metric key={`${row.label}-${index}`} label={row.label} value={row.value} valueTone={row.valueTone} />
            ))}
          </div>
        </section>

        <section className="ticker-research-section">
          <h3>Setups & benchmark context</h3>
          {detail.insight?.softBottoming && (
            <div className="ticker-active-setup">
              <div><span>Soft-bottoming setup</span><strong>{detail.insight.score.toFixed(2)}</strong></div>
              <p>{detail.insight.baseRate?.headline ?? 'Base rate is still calibrating.'} <span>This is measured, not a forecast.</span></p>
              <div className="ticker-setup-components">
                {detail.insight.components.map((component) => <span key={component.label} data-met={component.met}>{component.met ? 'Pass' : 'Watch'} · {component.label}</span>)}
              </div>
            </div>
          )}
          <div className="ticker-metric-table">
            {detail.verdict.map((row) => (
              <div key={row.bench} className="ticker-benchmark-row">
                <Metric label={`vs ${row.bench} · 52w`} value={`${row.label} · ${signedPercent(row.excessReturnPct)}`} valueTone={row.tone} />
                <span>{row.assetReturnPct == null || row.benchmarkReturnPct == null ? 'Insufficient overlapping history' : `${signedPercent(row.assetReturnPct)} vs ${signedPercent(row.benchmarkReturnPct)} · β ${row.beta?.toFixed(2) ?? '—'} · beta-adj. ${signedPercent(row.betaAdjustedExcessPct)}`}</span>
              </div>
            ))}
          </div>
        </section>

        {position && (
          <section className="ticker-research-section ticker-position-section">
            <h3>Current position</h3>
            <div className="ticker-position-metrics">
              <Metric label="Shares" value={position.shares == null ? '—' : position.shares.toLocaleString()} />
              <Metric label="Average cost" value={position.avgCost == null ? '—' : `$${position.avgCost.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} />
              <Metric label="Unrealized" value={signedPercent(position.pnlPct)} valueTone={tone(position.pnlPct)} />
              <Metric label="Portfolio weight" value={signedPercent(position.allocationPct)} />
            </div>
          </section>
        )}
      </div>

      <div className="ticker-risk-strip">
        <h3>Risk conditions · deterministic</h3>
        <p>{detail.kill}</p>
      </div>

      <footer className="ticker-provenance-row">
        <span>Price basis · split-adjusted</span>
        <span>History · {intelligence ? `${intelligence.dataQuality.historyWeeks.toLocaleString()} weeks` : '—'}</span>
        <span>Volume · {intelligence?.dataQuality.hasVolume ? 'available' : 'unavailable'}</span>
        {intelligence?.dataQuality.thinHistory && <strong>Thin history · trend confidence reduced</strong>}
        {latestMaterialEvidence(evidence) && <span>Material evidence available in SEC & Events</span>}
      </footer>
    </div>
  );
}

function Metric({ label, value, valueTone = 'flat' }: { label: string; value: string; valueTone?: Tone }) {
  return (
    <div className="ticker-metric-row">
      <span>{label}</span>
      <strong style={{ color: valueTone === 'flat' ? MM.textSoft : toneColor(valueTone), fontFamily: mono }}>{value}</strong>
    </div>
  );
}
