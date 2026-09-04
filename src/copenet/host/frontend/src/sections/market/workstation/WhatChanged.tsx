// "What changed" — the left column of the briefing.
//
// Every row answers a standing question — REGIME (what world am I in), MATTERS (what changed
// that I care about), MOVERS (what moved), BOOK (my money), NEXT 7D (what is coming), LEDGER
// (is any of this calibrated) — and renders only deltas; the standing picture is the column
// beside it. Matters is a ranked table, not a feed: the sweep's own composer orders it
// (flagged evidence → signal flips → rotation → the rest), the table shows six, and the
// footer says exactly what it cut. Honest empty states throughout: a quiet day says so.

import { useState, type ReactNode } from 'react';
import { ArrowUpRight } from 'lucide-react';
import type { MarketSection } from '../../../lib/appSectionRouting';
import { MATTERS_VISIBLE, composeMatters, observedPanelData, regimeLabel, truncationLabel } from '../marketBriefModel';
import { toneColor } from '../marketUi';
import type { MorningBriefPayload, Panel, Regime } from '../types';

const REGIME_COLOR: Record<string, string> = {
  'risk-on': 'var(--mkt-up)',
  'risk-off': 'var(--mkt-down)',
  chop: 'var(--mkt-muted)',
  'event-risk': 'var(--mkt-accent)',
};

function BriefRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mw-row">
      <span className="mw-row__label">{label}</span>
      <div className="mw-row__body">{children}</div>
    </div>
  );
}

function Matters({ brief, onOpen }: { brief: MorningBriefPayload; onOpen: (symbol: string) => void }) {
  const [all, setAll] = useState(false);
  const matters = composeMatters(brief);
  if (matters.length === 0) {
    return <span className="mw-quiet" style={{ fontStyle: 'italic' }}>Nothing thesis-relevant — no new filings, signal flips, or rotation moves.</span>;
  }
  const visible = all ? matters : matters.slice(0, MATTERS_VISIBLE);
  const truncated = matters.length > MATTERS_VISIBLE;
  return (
    <div className="mw-matters" role="table" aria-label="What changed since the last sweep">
      <div className="mw-matters__head" role="row" aria-hidden="true">
        <span>Signal</span><span>Why now</span><span>Source</span><span />
      </div>
      {visible.map((matter) => (
        <div key={matter.key} className="mw-matter" role="row">
          <button type="button" className="mw-matter__signal" onClick={() => onOpen(matter.symbol)} title={`Open ${matter.symbol}`}>
            <span className="mw-matter__kind">{matter.kind}</span>
            <span className="mw-matter__sym">{matter.symbol}</span>
          </button>
          <button
            type="button"
            className="mw-matter__text"
            onClick={() => onOpen(matter.symbol)}
            style={{ color: matter.tone === 'flat' ? undefined : toneColor(matter.tone) }}
            title={matter.text}
          >
            {matter.text}
          </button>
          <span className="mw-matter__source">{matter.source}</span>
          {matter.url ? (
            <a className="mw-matter__link" href={matter.url} target="_blank" rel="noreferrer" aria-label={`Open the filing for ${matter.symbol}`} title="Open the filing">
              <ArrowUpRight size={12} />
            </a>
          ) : (
            <span />
          )}
        </div>
      ))}
      {truncated && (
        <div className="mw-matters__foot">
          <span>{all ? `all ${matters.length}` : `${visible.length} of ${matters.length}`}</span>
          <button type="button" className="mw-more" onClick={() => setAll((value) => !value)}>
            {all ? `top ${MATTERS_VISIBLE} ↑` : truncationLabel(visible.length, matters.length).replace(/^.*· /, '')}
          </button>
        </div>
      )}
    </div>
  );
}

export function WhatChanged({
  brief,
  generating,
  briefUnavailable,
  regime,
  calendar,
  ledgerLine,
  onOpen,
  onExplain,
  onGoTo,
}: {
  brief: MorningBriefPayload | null;
  generating: boolean;
  briefUnavailable?: boolean;
  regime: Panel<Regime>;
  calendar: ReactNode;
  ledgerLine: string | null;
  onOpen: (symbol: string) => void;
  onExplain: () => void;
  onGoTo: (section: MarketSection) => void;
}) {
  const regimeCurrent = observedPanelData(regime)?.current ?? 'unknown';
  const movers = brief?.movers ?? [];

  return (
    <div className="mw-brief__changed">
      <BriefRow label="Regime">
        <span style={{ fontFamily: 'var(--mkt-mono)', fontSize: 'var(--mkt-t-value)', color: REGIME_COLOR[regimeCurrent] ?? 'var(--mkt-soft)' }}>
          {brief?.regimeShift
            ? `${regimeLabel(brief.regimeShift.from)} → ${regimeLabel(brief.regimeShift.to)} today`
            : regimeCurrent === 'unknown' ? 'No saved regime yet.' : `${regimeLabel(regimeCurrent)} — ${brief ? 'unchanged since last sweep' : 'current read'}`}
        </span>
        <button type="button" className="mw-more" style={{ marginLeft: 8 }} onClick={onExplain}>why →</button>
      </BriefRow>

      <BriefRow label="Matters">
        {brief ? (
          <Matters brief={brief} onOpen={onOpen} />
        ) : (
          <span className="mw-quiet">
            {briefUnavailable ? 'Saved briefing could not be loaded. Retry above.' : generating
              ? 'Building the first saved briefing…'
              : 'No saved briefing. Review your schedule or run a scan in Scans & alerts.'}
          </span>
        )}
      </BriefRow>

      {movers.length > 0 && (
        <BriefRow label="Movers">
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 5 }}>
            {movers.map((mover, index) => (
              <button key={`mv-${index}`} type="button" className="mw-mover" onClick={() => onOpen(mover.symbol)} title={mover.name}>
                <span>{mover.symbol}</span>
                <span style={{ color: toneColor(mover.tone) }}>{mover.changePct > 0 ? '+' : ''}{mover.changePct.toFixed(1)}%</span>
              </button>
            ))}
            <span className="mw-sect__meta">{brief?.moversLabel || 'last session'}</span>
          </div>
        </BriefRow>
      )}

      {brief?.portfolioNote && (
        <BriefRow label="Book">
          <span style={{ fontSize: 'var(--mkt-t-value)', color: 'var(--mkt-muted)' }}>{brief.portfolioNote}</span>
          <button type="button" className="mw-more" style={{ marginLeft: 8 }} onClick={() => onGoTo('portfolio')}>Portfolio →</button>
        </BriefRow>
      )}

      <BriefRow label="Next 7d">{calendar}</BriefRow>

      {ledgerLine && (
        <BriefRow label="Ledger">
          <span style={{ fontFamily: 'var(--mkt-mono)', fontSize: 'var(--mkt-t-value)', color: 'var(--mkt-muted)' }}>{ledgerLine}</span>
          <button type="button" className="mw-more" style={{ marginLeft: 8 }} onClick={() => onGoTo('ledger')}>open →</button>
        </BriefRow>
      )}
    </div>
  );
}
