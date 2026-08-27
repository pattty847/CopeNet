import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useIsMobile } from '../../lib/responsive';
import { wsClient } from '../../lib/wsClient';
import { MM, mono } from './marketUi';
import type { TreasuryYieldCurvePayload, TreasuryYieldPoint, YieldCurveRange } from './types';

const RANGE_LABELS: { value: YieldCurveRange; label: string }[] = [
  { value: '1d', label: '1D' },
  { value: '1w', label: '1W' },
  { value: '1m', label: '1M' },
];

function tone(value: number): string {
  return value > 0 ? MM.up : value < 0 ? MM.down : MM.muted;
}

function signedBps(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)} bps`;
}

function CurveChart({ points }: { points: TreasuryYieldPoint[] }) {
  const width = 760;
  const height = 292;
  const pad = { left: 52, right: 26, top: 28, bottom: 42 };
  const values = points.map((point) => point.yield);
  const minYears = Math.min(...points.map((point) => point.years));
  const maxYears = Math.max(...points.map((point) => point.years));
  const floor = Math.floor((Math.min(...values) - 0.2) * 2) / 2;
  const ceiling = Math.ceil((Math.max(...values) + 0.2) * 2) / 2;
  const span = Math.max(0.5, ceiling - floor);
  const x = (years: number) => pad.left + ((years - minYears) / Math.max(1, maxYears - minYears)) * (width - pad.left - pad.right);
  const y = (value: number) => pad.top + ((ceiling - value) / span) * (height - pad.top - pad.bottom);
  const path = points.map((point, index) => `${index ? 'L' : 'M'} ${x(point.years)} ${y(point.yield)}`).join(' ');
  const area = `${path} L ${x(points[points.length - 1].years)} ${height - pad.bottom} L ${x(points[0].years)} ${height - pad.bottom} Z`;
  const ticks = Array.from({ length: 4 }, (_, index) => ceiling - (index * span) / 3);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-labelledby="treasury-chart-title treasury-chart-description" style={{ width: '100%', minWidth: 620, height: 'auto', overflow: 'visible' }}>
      <title id="treasury-chart-title">United States Treasury yield curve</title>
      <desc id="treasury-chart-description">Treasury yields plotted on a linear maturity axis from three months through thirty years.</desc>
      <defs>
        <linearGradient id="treasury-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={MM.accent} stopOpacity=".18" />
          <stop offset="100%" stopColor={MM.accent} stopOpacity="0" />
        </linearGradient>
        <filter id="treasury-glow" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="3" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={pad.left} y1={y(tick)} x2={width - pad.right} y2={y(tick)} stroke="rgba(254,252,244,.07)" strokeDasharray="3 5" />
          <text x={pad.left - 10} y={y(tick) + 4} textAnchor="end" fill={MM.dim} fontFamily={mono} fontSize="10">{tick.toFixed(2)}%</text>
        </g>
      ))}
      <path d={area} fill="url(#treasury-area)" />
      <path d={path} fill="none" stroke={MM.accent} strokeWidth="2.5" strokeLinejoin="round" filter="url(#treasury-glow)" />
      {points.map((point, index) => (
        <g key={point.symbol}>
          <line x1={x(point.years)} y1={pad.top} x2={x(point.years)} y2={height - pad.bottom} stroke="rgba(254,252,244,.04)" />
          <circle cx={x(point.years)} cy={y(point.yield)} r="5" fill={MM.panel} stroke={MM.accent} strokeWidth="2" />
          <text x={x(point.years)} y={y(point.yield) - 13} textAnchor="middle" fill={MM.text} fontFamily={mono} fontSize="12" fontWeight="600">{point.yield.toFixed(2)}</text>
          <text x={x(point.years)} y={height - 15} textAnchor="middle" fill={MM.muted} fontFamily={mono} fontSize="11">{point.label}</text>
        </g>
      ))}
    </svg>
  );
}

function EmptyCurve({ loading, error, onRetry }: { loading: boolean; error: string | null; onRetry: () => void }) {
  return (
    <div role="status" aria-live="polite" style={{ minHeight: 330, display: 'grid', placeItems: 'center', textAlign: 'center', color: MM.dim }}>
      <div>
        <div style={{ fontSize: 24, marginBottom: 8 }}>{loading ? '◌' : '∿'}</div>
        <div style={{ fontSize: 12, color: MM.textSoft }}>{loading ? 'Loading the Treasury curve…' : 'Treasury curve unavailable'}</div>
        {error && <div style={{ fontSize: 10.5, marginTop: 5, maxWidth: 420 }}>{error}</div>}
        {!loading && <button onClick={onRetry} style={{ marginTop: 12, cursor: 'pointer', border: `1px solid ${MM.borderHi}`, borderRadius: 8, background: MM.accentSoft, color: MM.accent, padding: '6px 11px', font: '600 10px Inter' }}>Retry</button>}
      </div>
    </div>
  );
}

export function TreasuryYieldCurve() {
  const isMobile = useIsMobile();
  const [selectedRange, setSelectedRange] = useState<YieldCurveRange>('1d');
  const [curve, setCurve] = useState<TreasuryYieldCurvePayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const load = useCallback(async (nextRange: YieldCurveRange, refresh = false) => {
    const sequence = requestSequence.current + 1;
    requestSequence.current = sequence;
    setLoading(true);
    setError(null);
    setCurve(null);
    try {
      const next = await wsClient.marketYieldCurveGet(nextRange, refresh);
      if (requestSequence.current === sequence) setCurve(next);
    } catch (cause) {
      if (requestSequence.current === sequence) {
        setError(cause instanceof Error ? cause.message : 'U.S. Treasury did not return yield-curve data.');
      }
    } finally {
      if (requestSequence.current === sequence) setLoading(false);
    }
  }, []);

  useEffect(() => { void load(selectedRange); }, [load, selectedRange]);
  const asOf = useMemo(() => curve ? new Date(curve.asOf).toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric', timeZone: 'UTC' }) : '', [curve]);

  return (
    <section className="market-treasury-curve" aria-labelledby="treasury-curve-title" style={{ border: `1px solid ${MM.borderHi}`, borderRadius: 14, background: `radial-gradient(circle at 25% 20%, rgba(251,148,35,.055), transparent 34%), ${MM.panel}`, overflow: 'hidden' }}>
      <div className="market-treasury-curve__header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, borderBottom: `1px solid ${MM.border}`, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span aria-hidden="true" style={{ color: MM.accent, fontFamily: mono, fontSize: 18 }}>∿</span>
          <div>
            <h2 id="treasury-curve-title" style={{ margin: 0, font: '700 11px Inter', letterSpacing: '.14em', color: MM.text, textTransform: 'uppercase' }}>Treasury curve</h2>
            <div style={{ marginTop: 3, fontSize: 9.5, color: MM.dim }}>US government yields · {asOf || 'latest close'}</div>
          </div>
          {curve && <span style={{ border: '1px solid rgba(105,197,137,.25)', borderRadius: 999, padding: '2px 7px', color: MM.up, font: '700 8px Inter', letterSpacing: '.1em' }}>LATEST CLOSE</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div role="group" aria-label="Yield change range" style={{ display: 'flex', border: `1px solid ${MM.border}`, borderRadius: 8, padding: 2, background: '#050506' }}>
            {RANGE_LABELS.map((option) => (
              <button key={option.value} onClick={() => setSelectedRange(option.value)} aria-pressed={selectedRange === option.value} style={{ cursor: 'pointer', border: 'none', borderRadius: 6, minHeight: isMobile ? 44 : undefined, padding: isMobile ? '8px 12px' : '4px 9px', background: selectedRange === option.value ? MM.accentSoft : 'transparent', color: selectedRange === option.value ? MM.accent : MM.dim, font: '700 9px Inter' }}>{option.label}</button>
            ))}
          </div>
          <button onClick={() => void load(selectedRange, true)} disabled={loading} aria-label="Refresh Treasury curve" title="Refresh Treasury curve" style={{ cursor: loading ? 'default' : 'pointer', border: `1px solid ${MM.border}`, borderRadius: 7, minWidth: isMobile ? 44 : 28, minHeight: isMobile ? 44 : 26, background: 'transparent', color: MM.muted, opacity: loading ? .5 : 1 }}>↻</button>
          <a href={curve?.sourceUrl || 'https://home.treasury.gov/resource-center/data-chart-center/interest-rates'} target="_blank" rel="noreferrer" style={{ border: `1px solid ${MM.border}`, borderRadius: 7, padding: '4px 8px', color: MM.muted, font: '600 8px Inter', letterSpacing: '.1em', textDecoration: 'none' }}>US TREASURY</a>
        </div>
      </div>

      {!curve ? <EmptyCurve loading={loading} error={error} onRetry={() => void load(selectedRange)} /> : (
        <div style={{ display: 'grid', gridTemplateColumns: isMobile ? '1fr' : 'minmax(0, 2fr) minmax(260px, .8fr)' }}>
          <div className="market-treasury-curve__chart" style={{ minWidth: 0 }}>
            <div style={{ font: '600 8.5px Inter', letterSpacing: '.13em', color: MM.dim, textTransform: 'uppercase' }}>Yield (%)</div>
            <div style={{ overflowX: 'auto', paddingBottom: 2 }}><CurveChart points={curve.points} /></div>
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${curve.points.length}, minmax(76px, 1fr))`, border: `1px solid ${MM.border}`, borderRadius: 10, overflowX: 'auto' }}>
              {curve.points.map((point, index) => (
                <div key={point.symbol} title={point.name} style={{ padding: '10px 12px', borderLeft: index ? `1px solid ${MM.border}` : 'none', minWidth: 76 }}>
                  <div style={{ font: '700 9px Inter', color: MM.muted }}>{point.label}</div>
                  <div style={{ marginTop: 5, font: `600 15px ${mono}`, color: MM.text }}>{point.yield.toFixed(2)}%</div>
                  <div style={{ marginTop: 3, font: `600 9.5px ${mono}`, color: tone(point.changeBps) }}>{signedBps(point.changeBps)}</div>
                </div>
              ))}
            </div>
            <table style={{ position: 'absolute', width: 1, height: 1, padding: 0, margin: -1, overflow: 'hidden', clip: 'rect(0, 0, 0, 0)', whiteSpace: 'nowrap', border: 0 }}>
              <caption>Treasury yields and {selectedRange.toUpperCase()} changes as of {asOf}</caption>
              <thead><tr><th>Maturity</th><th>Yield</th><th>Change in basis points</th></tr></thead>
              <tbody>{curve.points.map((point) => <tr key={point.symbol}><th>{point.label}</th><td>{point.yield.toFixed(2)}%</td><td>{signedBps(point.changeBps)}</td></tr>)}</tbody>
            </table>
          </div>

          <aside className="market-treasury-curve__insights" aria-label="Treasury curve insights" style={{ borderLeft: isMobile ? 'none' : `1px solid ${MM.border}`, borderTop: isMobile ? `1px solid ${MM.border}` : 'none', display: 'flex', flexDirection: 'column' }}>
            <div className="market-treasury-curve__insight-card" style={{ border: `1px solid ${MM.border}`, borderRadius: 11, background: MM.panelInset }}>
              <div style={{ font: '700 8.5px Inter', letterSpacing: '.14em', color: MM.accent, textTransform: 'uppercase' }}>Curve shape</div>
              <div style={{ marginTop: 8, font: '500 19px Inter', color: MM.text }}>{curve.shape.label}</div>
              <div style={{ marginTop: 7, fontSize: 10.5, lineHeight: 1.55, color: MM.muted }}>{curve.shape.detail}</div>
            </div>
            <div className="market-treasury-curve__insight-card" style={{ border: `1px solid ${MM.border}`, borderRadius: 11, background: MM.panelInset }}>
              <div style={{ font: '700 8.5px Inter', letterSpacing: '.14em', color: MM.accent, textTransform: 'uppercase', marginBottom: 7 }}>Key spreads</div>
              {curve.spreads.map((spread) => (
                <div key={spread.label} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, padding: '7px 0', borderTop: `1px solid ${MM.border}` }}>
                  <span style={{ fontSize: 11, color: MM.textSoft }}>{spread.label}</span>
                  <span style={{ font: `600 11px ${mono}`, color: tone(spread.valueBps) }}>{signedBps(spread.valueBps)}</span>
                </div>
              ))}
            </div>
            <div className="market-treasury-curve__insight-card" style={{ border: `1px solid ${MM.border}`, borderRadius: 11, background: MM.panelInset, flex: 1 }}>
              <div style={{ font: '700 8.5px Inter', letterSpacing: '.14em', color: MM.accent, textTransform: 'uppercase' }}>Why it matters</div>
              <p style={{ margin: '9px 0 0', fontSize: 10.5, lineHeight: 1.55, color: MM.textSoft }}>The curve prices expectations for growth, inflation, and Federal Reserve policy across time.</p>
              <p style={{ margin: '8px 0 0', fontSize: 10.5, lineHeight: 1.55, color: MM.muted }}>Watch the 10Y–2Y spread for the policy cycle and 10Y–3M for deeper inversion risk.</p>
            </div>
            <div style={{ fontSize: 8.5, lineHeight: 1.45, color: MM.dimmer }}>{curve.coverageNote}</div>
          </aside>
        </div>
      )}
    </section>
  );
}
