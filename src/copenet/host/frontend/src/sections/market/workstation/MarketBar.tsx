// The market bar: what stays true while the subject changes.
//
// Regime, freshness, VIX and breadth are the only market facts that belong in chrome — they
// colour how every other number is read. Actions here act on the whole page (refresh, jump,
// density); anything that acts on one section lives in that section.

import { Search } from 'lucide-react';
import { NextScanControl } from '../monitoring/NextScanControl';
import type { Density } from '../marketWorkstationState';
import { formatBreadth, formatVix, regimeLabel } from '../marketBriefModel';

const REGIME_COLORS: Record<string, string> = {
  'risk-off': 'var(--mkt-down)',
  chop: 'var(--mkt-muted)',
  'risk-on': 'var(--mkt-up)',
  'event-risk': 'var(--mkt-accent)',
};

export function MarketBar({
  regime,
  regimeReasoning,
  live,
  asOf,
  vix,
  breadthPct,
  onRefresh,
  density,
  onDensity,
  onJump,
}: {
  regime: string;
  regimeReasoning?: string;
  live: boolean;
  asOf: string;
  vix: number;
  breadthPct: number;
  onRefresh: () => void;
  density: Density;
  onDensity: (density: Density) => void;
  onJump: () => void;
}) {
  return (
    <header className="mw-bar">
      <div className="mw-bar__identity">
        <h1 className="mw-bar__title">Market</h1>
        <span className="mw-bar__sub">slow-timeframe radar</span>
      </div>

      <span className="mw-regime" style={{ color: REGIME_COLORS[regime] ?? 'var(--mkt-soft)' }} title={regimeReasoning || 'Current regime read'}>
        <span className="mw-regime__dot" />
        {regimeLabel(regime)}
      </span>

      <span className="mw-freshness" role="status">
        <span className="mw-freshness__dot" style={{ background: live ? 'var(--mkt-up)' : 'var(--mkt-dim)' }} />
        {live ? asOf : 'illustrative preview'}
      </span>

      <div className="mw-bar__spacer" />

      <div className="mw-bar__stat" title="CBOE Volatility Index">
        <b>{formatVix(vix)}</b>
        <span>VIX</span>
      </div>
      <div className="mw-bar__stat" title="Share of tracked names above their weekly trend">
        <b>{formatBreadth(breadthPct)}</b>
        <span>Breadth</span>
      </div>

      <span className="tw-sep" />

      <div className="mw-density" role="group" aria-label="Density">
        <button type="button" aria-pressed={density === 'compact'} onClick={() => onDensity('compact')} title="Compact density">Compact</button>
        <button type="button" aria-pressed={density === 'comfortable'} onClick={() => onDensity('comfortable')} title="Comfortable density">Comfortable</button>
      </div>

      <NextScanControl onOpen={onRefresh} />
      <button type="button" className="tw-iconbtn" onClick={onJump} title="Jump to symbol ( / )" aria-label="Jump to symbol">
        <Search size={14} />
      </button>
    </header>
  );
}
