// The standing picture — what the market IS while the brief says what changed.
//
// Deliberately quieter than the brief: macro references as a seamed tile grid, the rate
// complex reduced to shape + key spreads, and flagged setups only when the deterministic
// screens actually flag something (soft bottoming is rare by design — an empty section
// stays silent instead of apologising). Every deeper question this column raises has a
// named door into the research dock.

import { useEffect, useState } from 'react';
import { wsClient } from '../../lib/wsClient';
import { PreviewBadge, toneColor } from './marketUi';
import { Sparkline } from './workspaceViz';
import type { MarketDockTab } from './marketCockpitState';
import type { DashboardPayload, TreasuryYieldCurvePayload } from './types';

/** One quiet fetch for the rates stub. The Rates dock tab owns the full curve view (and
 *  its own fetch); this stub only answers "what shape, which way" at a glance. */
function useYieldCurveStub() {
  const [curve, setCurve] = useState<TreasuryYieldCurvePayload | null>(null);
  useEffect(() => {
    let alive = true;
    wsClient
      .marketYieldCurveGet('1d', false)
      .then((next) => {
        if (alive) setCurve(next);
      })
      .catch(() => {
        /* offline or upstream down — the row simply doesn't render */
      });
    return () => {
      alive = false;
    };
  }, []);
  return curve;
}

function signedBps(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(0)} bps`;
}

export function TapeColumn({
  dash,
  onOpen,
  openDock,
}: {
  dash: DashboardPayload;
  onOpen: (symbol: string) => void;
  openDock: (tab: MarketDockTab) => void;
}) {
  const curve = useYieldCurveStub();
  // The stub shows the flags, not the study: soft bottoming in full (rare by design),
  // trend flips capped — the Signals tab owns the complete list.
  const softBottoming = (dash.softBottoming?.data ?? []).slice(0, 6);
  const allTrend = dash.trend?.data ?? [];
  const trend = allTrend.slice(0, 5);
  const trendOverflow = allTrend.length - trend.length;
  const tenYear = curve?.points.find((point) => point.label === '10Y');

  return (
    <aside className="mc-tape" aria-label="Standing picture">
      <div className="mc-tape__section">
        <div className="mc-sect">
          <span className="mc-sect__label">Tape</span>
          <span className="mc-sect__meta">5-day · close</span>
          <span className="mc-sect__spacer" />
          <PreviewBadge status={dash.macro.status} />
        </div>
        <div className="mc-tiles">
          {dash.macro.data.map((item) => (
            <div key={item.label} className="mc-tile">
              <span className="mc-tile__k">{item.label}</span>
              <span className="mc-tile__v">{item.value}</span>
              <span className="mc-tile__delta">
                <span style={{ color: toneColor(item.tone) }}>{item.change}</span>
                <span style={{ width: 44, flex: '0 0 auto' }}>
                  <Sparkline points={item.spark} color={toneColor(item.tone)} height={14} />
                </span>
              </span>
            </div>
          ))}
        </div>
      </div>

      {curve && (
        <div className="mc-tape__section">
          <div className="mc-sect">
            <span className="mc-sect__label">Rates</span>
            <span className="mc-sect__meta">{curve.shape.label}</span>
            <span className="mc-sect__spacer" />
            <button type="button" className="mc-open" onClick={() => openDock('rates')}>Curve →</button>
          </div>
          <div className="mc-kv-list">
            {tenYear && (
              <div className="mc-kv">
                <span className="mc-kv__k">US 10Y</span>
                <span className="mc-kv__v">
                  {tenYear.yield.toFixed(2)}%{' '}
                  <span style={{ color: tenYear.changeBps > 0 ? 'var(--mkt-up)' : tenYear.changeBps < 0 ? 'var(--mkt-down)' : 'var(--mkt-dim)' }}>
                    {signedBps(tenYear.changeBps)}
                  </span>
                </span>
              </div>
            )}
            {curve.spreads.map((spread) => (
              <div key={spread.label} className="mc-kv">
                <span className="mc-kv__k">{spread.label}</span>
                <span className="mc-kv__v" style={{ color: spread.valueBps >= 0 ? 'var(--mkt-up)' : 'var(--mkt-down)' }}>
                  {signedBps(spread.valueBps)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(softBottoming.length > 0 || trend.length > 0) && (
        <div className="mc-tape__section">
          <div className="mc-sect">
            <span className="mc-sect__label">Flagged setups</span>
            {softBottoming.length > 0 && <span className="mc-sect__meta">{dash.softBottoming?.note ?? 'calibrated · 8w'}</span>}
            <span className="mc-sect__spacer" />
            <button type="button" className="mc-open" onClick={() => openDock('signals')}>Signals →</button>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {softBottoming.map((item) => (
              <button key={`sb-${item.symbol}`} type="button" className="mc-setup" onClick={() => onOpen(item.symbol)} title={item.name}>
                <span className="mc-setup__sym">{item.symbol}</span>
                <span style={{ color: 'var(--mkt-up)' }}>soft bottoming · {item.score.toFixed(2)}</span>
                <span style={{ marginLeft: 'auto', color: 'var(--mkt-dim)' }}>{item.drawdown} dd · RSI {item.rsi}</span>
              </button>
            ))}
            {trend.map((item) => (
              <button
                key={`tr-${item.symbol}`}
                type="button"
                className="mc-setup"
                style={{ borderLeftColor: item.direction === 'up' ? 'rgba(105,197,137,.5)' : 'rgba(217,109,95,.5)' }}
                onClick={() => onOpen(item.symbol)}
              >
                <span className="mc-setup__sym">{item.symbol}</span>
                <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: item.direction === 'up' ? 'var(--mkt-up)' : 'var(--mkt-down)' }}>
                  {item.direction === 'up' ? '↑' : '↓'} {item.note}
                </span>
              </button>
            ))}
            {trendOverflow > 0 && (
              <button type="button" className="mc-more" onClick={() => openDock('signals')}>
                +{trendOverflow} more in Signals →
              </button>
            )}
          </div>
        </div>
      )}

      <div className="mc-tape__section">
        <div className="mc-sect" style={{ marginBottom: 2 }}>
          <span className="mc-sect__label">Investigate</span>
        </div>
        <div className="mc-kv-list">
          <div className="mc-kv">
            <span className="mc-kv__k">Sector &amp; industry rotation</span>
            <button type="button" className="mc-open" onClick={() => openDock('rotation')}>Rotation →</button>
          </div>
          <div className="mc-kv">
            <span className="mc-kv__k">Positions, P&amp;L, trade history</span>
            <button type="button" className="mc-open" onClick={() => openDock('portfolio')}>Portfolio →</button>
          </div>
          <div className="mc-kv">
            <span className="mc-kv__k">Filings, insiders, thesis-killers</span>
            <button type="button" className="mc-open" onClick={() => openDock('evidence')}>Evidence →</button>
          </div>
          <div className="mc-kv">
            <span className="mc-kv__k">Portfolio backtests &amp; stress scenarios</span>
            <button type="button" className="mc-open" onClick={() => openDock('backtest')}>Backtest →</button>
          </div>
        </div>
      </div>
    </aside>
  );
}
