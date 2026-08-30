// Overview — the hybrid.
//
// Top half is visual: a number with a SHAPE gets drawn, because a 52-week range is a
// position within a band and printing "$206.96 – $404.47" throws that away. Bottom half is
// Codex's dense listing, because once you have read the shape you want the exact figures in
// a compact table, not four more charts. Visual first, precise second, and each in the form
// that suits it.

import { MM, mono, toneColor } from './marketUi';
import { Card, EmptyNote, KeyValue, Meter, RangeBand, ReturnsStrip, signedPct, toneHex, toneOf } from './workspaceViz';
import type { AssetProfile } from './assetProfile';
import type { EvidenceItem, TickerDetailPayload, Tone } from './types';

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

export function TabOverview({ detail, profile }: { detail: TickerDetailPayload; profile: AssetProfile }) {
  const intel = detail.intelligence;
  if (!intel) return <EmptyNote>No deterministic readout is available for this asset.</EmptyNote>;

  const { trend, momentum, returns, drawdown, volatility, structure } = intel;
  const stats = detail.stats;
  const exposure = intel.exposure;

  return (
    <div className="ticker-overview-panel" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <ReturnsStrip
        cells={[
          { k: '1W', v: returns.r1wPct },
          { k: '4W', v: returns.r4wPct },
          { k: '13W', v: returns.r13wPct },
          { k: '26W', v: returns.r26wPct },
          { k: 'YTD', v: returns.rYtdPct },
          { k: '52W', v: returns.r52wPct },
          { k: '3Y', v: returns.r3yPct },
        ]}
      />

      <div className="tw-grid">
        <Card title="52-week range">
          <RangeBand
            low={stats?.yearLow}
            high={stats?.yearHigh}
            value={detail.quote.price}
            lowLabel={stats?.yearLow != null ? `$${stats.yearLow.toFixed(2)}` : '—'}
            highLabel={stats?.yearHigh != null ? `$${stats.yearHigh.toFixed(2)}` : '—'}
          />
          <KeyValue k="Position in range" v={drawdown.pctOf52wRange == null ? '—' : `${drawdown.pctOf52wRange.toFixed(0)}%`} />
          {stats?.marketCap != null && <KeyValue k="Market cap" v={formatBigNumber(stats.marketCap, '$')} />}
          {stats?.avgVolume3m != null && <KeyValue k="Average volume · 3m" v={formatBigNumber(stats.avgVolume3m)} />}
        </Card>

        <Card title="Drawdown">
          <Meter fraction={Math.abs(drawdown.drawdown52wPct ?? 0) / 60} color={MM.down} label="From 52-week high" value={signedPct(drawdown.drawdown52wPct)} />
          <KeyValue k="Weeks since high" v={drawdown.weeksSince52wHigh == null ? '—' : `${drawdown.weeksSince52wHigh}`} />
          <KeyValue k="From all-time high" v={signedPct(drawdown.distFromFullHistoryHighPct)} tone={toneOf(drawdown.distFromFullHistoryHighPct)} />
        </Card>

        <Card title="Trend">
          <KeyValue k="Long trend" v={trend.longTrend ?? '—'} />
          <KeyValue k="MA stack" v={trend.maStack ?? '—'} />
          <KeyValue k="Distance from 40w MA" v={signedPct(trend.distMa40Pct)} tone={toneOf(trend.distMa40Pct)} />
          {structure.compression && (
            <span style={{ alignSelf: 'flex-start', border: '1px solid rgba(143,184,232,.28)', borderRadius: 4, padding: '2px 7px', color: MM.info, font: '600 9px Inter', letterSpacing: '.1em', textTransform: 'uppercase' }}>
              {structure.compressionShape ?? 'range'} compression
            </span>
          )}
        </Card>

        <Card title="Momentum & volatility">
          <Meter
            fraction={(momentum.rsi14 ?? 50) / 100}
            color={momentum.rsi14 == null ? MM.dim : momentum.rsi14 > 70 ? MM.down : momentum.rsi14 < 30 ? MM.up : MM.info}
            label="RSI 14"
            value={momentum.rsi14 == null ? '—' : momentum.rsi14.toFixed(0)}
          />
          <Meter fraction={(momentum.volVsAvg ?? 1) / 3} color={MM.info} label="Volume vs average" value={momentum.volVsAvg == null ? '—' : `${momentum.volVsAvg.toFixed(1)}×`} />
          <KeyValue k="Realized vol · 13w" v={signedPct(volatility.vol13wAnnualizedPct)} />
          <KeyValue k="ATR move" v={momentum.atrMoveMultiple == null ? '—' : `${momentum.atrMoveMultiple.toFixed(1)}× ATR`} />
        </Card>

        {intel.portfolio && (
          <Card title="Your position">
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 9 }}>
              <span style={{ fontFamily: mono, fontSize: 17, color: toneHex(toneOf(intel.portfolio.pnlPct)) }}>{signedPct(intel.portfolio.pnlPct)}</span>
              <span style={{ fontSize: 10, color: MM.dim }}>unrealized</span>
            </div>
            <KeyValue k="Shares" v={intel.portfolio.shares == null ? '—' : intel.portfolio.shares.toLocaleString()} />
            <KeyValue k="Average cost" v={intel.portfolio.avgCost == null ? '—' : `$${intel.portfolio.avgCost.toLocaleString(undefined, { maximumFractionDigits: 2 })}`} />
            <KeyValue k="Portfolio weight" v={signedPct(intel.portfolio.allocationPct)} />
          </Card>
        )}
      </div>

      {/* Codex's dense listings: exact figures once the shapes above have been read. */}
      <div className="ticker-overview-columns">
        {detail.signals.length > 0 && (
          <section className="ticker-research-section">
            <h3>Measured state · fixed horizons</h3>
            <div className="ticker-metric-table">
              {detail.signals.map((row, index) => <Metric key={`${row.key}-${index}`} label={row.key} value={row.value} valueTone={row.tone} />)}
            </div>
          </section>
        )}

        <section className="ticker-research-section">
          <h3>Setups &amp; benchmark context</h3>
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
                <Metric label={`vs ${row.bench} · 52w`} value={`${row.label} · ${signedPct(row.excessReturnPct)}`} valueTone={row.tone} />
                <span>
                  {row.assetReturnPct == null || row.benchmarkReturnPct == null
                    ? 'Insufficient overlapping history'
                    : `${signedPct(row.assetReturnPct)} vs ${signedPct(row.benchmarkReturnPct)} · β ${row.beta?.toFixed(2) ?? '—'} · beta-adj. ${signedPct(row.betaAdjustedExcessPct)}`}
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* A fund has no issuer tabs, so what it actually IS lives here. */}
        {profile.kind === 'fund' && exposure && (
          <section className="ticker-research-section">
            <h3>Fund exposure</h3>
            {exposure.topHoldings && exposure.topHoldings.length > 0 && (
              <div className="ticker-metric-table">
                {exposure.topHoldings.slice(0, 10).map((holding) => (
                  <Metric key={holding.symbol} label={`${holding.symbol}${holding.name ? ` · ${holding.name}` : ''}`} value={holding.weightPct == null ? '—' : `${holding.weightPct.toFixed(1)}%`} />
                ))}
              </div>
            )}
            {exposure.sectorWeightPct && Object.keys(exposure.sectorWeightPct).length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 8 }}>
                {Object.entries(exposure.sectorWeightPct)
                  .sort((a, b) => b[1] - a[1])
                  .map(([sector, weight]) => <Meter key={sector} fraction={weight / 100} color={MM.info} label={sector} value={`${weight.toFixed(1)}%`} />)}
              </div>
            )}
          </section>
        )}
      </div>

      <div className="ticker-risk-strip">
        <h3>Risk conditions · deterministic</h3>
        <p>{detail.kill}</p>
      </div>

      <footer className="ticker-provenance-row">
        <span>Price basis · split-adjusted</span>
        <span>History · {intel.dataQuality.historyWeeks.toLocaleString()} weeks</span>
        <span>Volume · {intel.dataQuality.hasVolume ? 'available' : 'unavailable'}</span>
        {intel.dataQuality.thinHistory && <strong>Thin history · trend confidence reduced</strong>}
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
