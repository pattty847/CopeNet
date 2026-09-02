// The standing picture — what the market IS while the brief says what changed.
//
// Deliberately quieter than the delta rows: the regime scale with its two numbers, the
// cross-asset tape as a dense grid at the working number size, the rate complex reduced to
// shape plus key spreads, the rotation map as quadrant chips, and calibrated setups only when
// a screen actually flags one. Every block has one door into the section that owns the fact,
// and nothing here is repeated in a section list under another name.

import { useEffect, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import type { MarketSection } from '../../../lib/appSectionRouting';
import { REGIME_ORDER, RRG_QUADRANTS, flaggedSetups, formatBreadth, formatVix, regimeLabel, rotationQuadrants } from '../marketBriefModel';
import { PreviewBadge, toneColor } from '../marketUi';
import { Sparkline } from '../workspaceViz';
import type { DashboardPayload, MarketRead, TreasuryYieldCurvePayload } from '../types';

/** One quiet fetch for the rates stub. Structure owns the full curve view (and its own
 *  fetch); this stub only answers "what shape, which way" at a glance. */
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
        /* offline or upstream down — the block simply doesn't render */
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

function Block({ label, meta, door, children }: { label: string; meta?: string; door?: { label: string; onClick: () => void }; children: React.ReactNode }) {
  return (
    <div className="mw-standing__block">
      <div className="mw-sect" style={{ marginBottom: 4 }}>
        <span className="mw-sect__label">{label}</span>
        {meta && <span className="mw-sect__meta">{meta}</span>}
        <span className="mw-sect__spacer" />
        {door && <button type="button" className="mw-open" onClick={door.onClick}>{door.label}</button>}
      </div>
      {children}
    </div>
  );
}

export function StandingPicture({
  dashboard,
  read,
  onOpen,
  onGoTo,
}: {
  dashboard: DashboardPayload;
  read: MarketRead | null;
  onOpen: (symbol: string) => void;
  onGoTo: (section: MarketSection) => void;
}) {
  const curve = useYieldCurveStub();
  const briefing = dashboard.briefing.data;
  const activeRegime = read?.regime ?? dashboard.regime.data.current;
  const quadrants = rotationQuadrants(dashboard.rrg.data);
  const setups = flaggedSetups(dashboard);
  const tenYear = curve?.points.find((point) => point.label === '10Y');

  return (
    <aside className="mw-brief__standing" aria-label="Standing picture">
      <Block label="Regime" meta={read ? 'model read' : 'computed'}>
        <div className="mw-regime-scale" aria-label={`Current regime: ${regimeLabel(activeRegime)}`}>
          {REGIME_ORDER.map((regime) => (
            <div key={regime} data-active={activeRegime === regime}>
              <span />
              <small>{regimeLabel(regime)}</small>
            </div>
          ))}
        </div>
        <div className="mw-regime-metrics">
          <div><b>{formatVix(briefing.vix)}</b><span>VIX</span></div>
          <div><b>{formatBreadth(briefing.breadthPct)}</b><span>Breadth</span></div>
        </div>
      </Block>

      <Block label="Tape" meta="5-day · close">
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 4 }}><PreviewBadge status={dashboard.macro.status} /></div>
        <div className="mw-tiles">
          {dashboard.macro.data.map((item) => (
            <div key={item.label} className="mw-tile">
              <span className="mw-tile__k">{item.label}</span>
              <span className="mw-tile__v">{item.value}</span>
              <span className="mw-tile__delta">
                <span style={{ color: toneColor(item.tone) }}>{item.change}</span>
                <span>{item.spark.length > 1 && <Sparkline points={item.spark} color={toneColor(item.tone)} height={12} />}</span>
              </span>
            </div>
          ))}
        </div>
      </Block>

      {curve && (
        <Block label="Rates" meta={curve.shape.label} door={{ label: 'Curve →', onClick: () => onGoTo('structure') }}>
          <div className="mw-kv-list">
            {tenYear && (
              <div className="mw-kv">
                <span className="mw-kv__k">US 10Y</span>
                <span className="mw-kv__v">
                  {tenYear.yield.toFixed(2)}%{' '}
                  <span style={{ color: tenYear.changeBps > 0 ? 'var(--mkt-up)' : tenYear.changeBps < 0 ? 'var(--mkt-down)' : 'var(--mkt-dim)' }}>{signedBps(tenYear.changeBps)}</span>
                </span>
              </div>
            )}
            {curve.spreads.map((spread) => (
              <div key={spread.label} className="mw-kv">
                <span className="mw-kv__k">{spread.label}</span>
                <span className="mw-kv__v" style={{ color: spread.valueBps >= 0 ? 'var(--mkt-up)' : 'var(--mkt-down)' }}>{signedBps(spread.valueBps)}</span>
              </div>
            ))}
          </div>
        </Block>
      )}

      <Block label="Rotation" meta="vs S&P 500 · weekly" door={{ label: 'Rotation →', onClick: () => onGoTo('structure') }}>
        <div className="mw-quadrants">
          {RRG_QUADRANTS.map((quadrant) => (
            <div key={quadrant} className="mw-quadrant" data-quadrant={quadrant}>
              <span>{quadrant}</span>
              <div>
                {quadrants[quadrant].length === 0 && <small>—</small>}
                {quadrants[quadrant].map((sector) => (
                  <button key={sector.symbol} type="button" onClick={() => onOpen(sector.symbol)} title={sector.name}>{sector.symbol}</button>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Block>

      {setups.length > 0 && (
        <Block label="Flagged setups" meta={dashboard.softBottoming.note ?? 'calibrated · 8w'} door={{ label: 'Signals →', onClick: () => onGoTo('signals') }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {setups.map((item) => (
              <button key={item.symbol} type="button" className="mw-setup" onClick={() => onOpen(item.symbol)} title={item.name}>
                <span className="mw-setup__sym">{item.symbol}</span>
                <span style={{ color: 'var(--mkt-up)' }}>soft bottoming · {item.score.toFixed(2)}</span>
                <span style={{ marginLeft: 'auto', color: 'var(--mkt-dim)' }}>{item.drawdown} dd · RSI {item.rsi}</span>
              </button>
            ))}
          </div>
        </Block>
      )}
    </aside>
  );
}
