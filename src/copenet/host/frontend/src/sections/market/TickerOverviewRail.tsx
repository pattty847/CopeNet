import type { ReactNode } from 'react';
import { MM, mono, toneColor } from './marketUi';
import type { EvidenceItem, TickerDetailPayload, Tone } from './types';

function signedPercent(value?: number | null, digits = 1): string {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

function tone(value?: number | null): Tone {
  return value == null || value === 0 ? 'flat' : value > 0 ? 'up' : 'down';
}

function latestMaterialEvidence(items: EvidenceItem[]): EvidenceItem | null {
  return [...items]
    .filter((item) => item.flag || item.type === 'Insider' || item.type === '8-K')
    .sort((a, b) => (b.t ?? 0) - (a.t ?? 0))[0] ?? null;
}

export function TickerOverviewRail({ detail, evidence }: { detail: TickerDetailPayload; evidence: EvidenceItem[] }) {
  const intelligence = detail.intelligence;
  const recentEvidence = latestMaterialEvidence(evidence);
  const position = intelligence?.portfolio;
  const whyNow = recentEvidence
    ? `${recentEvidence.type}: ${recentEvidence.headline}`
    : detail.insight?.softBottoming
      ? `Soft-bottoming setup is active with a ${detail.insight.score.toFixed(2)} score.`
      : position
        ? 'This asset is part of the current portfolio.'
        : 'Opened for a closer read from the Market cockpit.';

  return (
    <aside className="ticker-context-rail" aria-label="Asset context">
      <RailSection label="Why this asset now" accent={MM.accent}>
        <p style={{ margin: 0, fontSize: 12.5, color: MM.textSoft, lineHeight: 1.55 }}>{whyNow}</p>
      </RailSection>

      <RailSection label="Market state">
        <Metric label="Long trend" value={intelligence?.trend.longTrend ?? '—'} />
        <Metric label="13w excess vs VOO" value={signedPercent(intelligence?.relativeStrength.excessReturn13wPct)} valueTone={tone(intelligence?.relativeStrength.excessReturn13wPct)} />
        <Metric label="52w drawdown" value={signedPercent(intelligence?.drawdown.drawdown52wPct)} valueTone={tone(intelligence?.drawdown.drawdown52wPct)} />
        <Metric label="13w realized vol" value={signedPercent(intelligence?.volatility.vol13wAnnualizedPct)} />
        {intelligence?.structure.compression && (
          <span style={{ display: 'inline-flex', alignSelf: 'flex-start', border: `1px solid ${MM.borderHi}`, borderRadius: 999, padding: '3px 8px', color: MM.accent, font: '600 9px Inter', letterSpacing: '.06em', textTransform: 'uppercase' }}>
            {intelligence.structure.compressionShape ?? 'range'} compression
          </span>
        )}
      </RailSection>

      <RailSection label={position ? 'Your position' : 'Portfolio context'} accent={position ? '#8fb8e8' : undefined}>
        {position ? (
          <>
            <Metric label="Shares" value={position.shares == null ? '—' : position.shares.toLocaleString()} />
            <Metric label="Average cost" value={position.avgCost == null ? '—' : `$${position.avgCost.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} />
            <Metric label="Unrealized" value={signedPercent(position.pnlPct)} valueTone={tone(position.pnlPct)} />
            <Metric label="Portfolio weight" value={signedPercent(position.allocationPct)} />
          </>
        ) : (
          <p style={{ margin: 0, fontSize: 11.5, color: MM.dim, lineHeight: 1.5 }}>Not present in the latest synced portfolio snapshot.</p>
        )}
      </RailSection>

      {detail.verdict.length > 0 && (
        <RailSection label="Benchmark check">
          {detail.verdict.map((row) => (
            <div key={row.bench} style={{ display: 'grid', gap: 3 }}>
              <Metric label={`vs ${row.bench} · 52w`} value={`${row.label} · ${signedPercent(row.excessReturnPct)}`} valueTone={row.tone} />
              <span style={{ color: MM.dimmer, fontFamily: mono, fontSize: 9, lineHeight: 1.4, textAlign: 'right' }}>
                {row.assetReturnPct == null || row.benchmarkReturnPct == null
                  ? 'Insufficient overlapping history'
                  : `${signedPercent(row.assetReturnPct)} vs ${signedPercent(row.benchmarkReturnPct)} · β ${row.beta?.toFixed(2) ?? '—'} · beta-adj. ${signedPercent(row.betaAdjustedExcessPct)}`}
              </span>
            </div>
          ))}
        </RailSection>
      )}

      <RailSection label="Data integrity">
        <Metric label="Price basis" value="Split-adjusted" />
        <Metric label="History" value={intelligence ? `${intelligence.dataQuality.historyWeeks.toLocaleString()} weeks` : '—'} />
        <Metric label="Volume" value={intelligence?.dataQuality.hasVolume ? 'Available' : 'Unavailable'} />
        {intelligence?.dataQuality.thinHistory && <span style={{ fontSize: 10.5, color: MM.down }}>Thin history — trend conclusions are lower confidence.</span>}
      </RailSection>
    </aside>
  );
}

function RailSection({ label, accent = MM.muted, children }: { label: string; accent?: string; children: ReactNode }) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: 13, borderRadius: 12, border: `1px solid ${MM.border}`, background: 'rgba(254,252,244,.018)' }}>
      <h3 style={{ margin: 0, font: '650 9px Inter', letterSpacing: '.13em', textTransform: 'uppercase', color: accent }}>{label}</h3>
      {children}
    </section>
  );
}

function Metric({ label, value, valueTone = 'flat' }: { label: string; value: string; valueTone?: Tone }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
      <span style={{ fontSize: 10.5, color: MM.dim }}>{label}</span>
      <span style={{ fontFamily: mono, fontSize: 10.5, color: valueTone === 'flat' ? MM.textSoft : toneColor(valueTone), textAlign: 'right', textTransform: label === 'Long trend' ? 'capitalize' : undefined }}>{value}</span>
    </div>
  );
}
