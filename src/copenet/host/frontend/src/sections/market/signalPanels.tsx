// The three screens, rendered so a row explains itself.
//
// The shape is the same for each: the RULE the screen tests, then what happened the LAST TIME
// it fired (where the screen is calibrated), then per row the CONDITIONS that actually fired.
// Extracted from panelsLists.tsx, which now keeps only the portfolio panels.

import { useState, type ReactNode } from 'react';
import type { AccumulationRow, Panel, ScreenCalibration, SoftBottomItem, TrendRow } from './types';
import { MM, PanelCard, mono, valueTone } from './marketUi';
import {
  CONFLUENCE_LABELS,
  SB_TEST_LABELS,
  calibrationRead,
  drawdownBand,
  regimeRead,
  rsiBand,
  sampleWindow,
  trendAge,
  type Band,
} from './screenReadings';

/** The screen's rule, stated once above its rows. A screen whose rule is not on the page is a
 *  list of tickers with no argument attached. */
function ScreenRule({ children }: { children: ReactNode }) {
  return <div style={{ fontSize: 11.5, color: MM.faint, lineHeight: 1.5, marginBottom: 12 }}>{children}</div>;
}

/** A number and the word for where it sits. `notable` is the end of the range the screen hunts
 *  in, so the eye can skip everything else. */
function Reading({ value, band, tone }: { value: string; band: Band | null; tone?: string }) {
  return (
    <span style={{ fontFamily: mono, fontSize: 10.5, color: tone ?? MM.textSoft, whiteSpace: 'nowrap' }}>
      {value}
      {band && (
        <span style={{ color: band.notable ? MM.accent : MM.dimmer, marginLeft: 5 }}>{band.word}</span>
      )}
    </span>
  );
}

function Chip({ label, title, on = true }: { label: string; title?: string; on?: boolean }) {
  return (
    <span
      title={title}
      style={{
        fontFamily: mono,
        fontSize: 9.5,
        padding: '2px 7px',
        borderRadius: 5,
        whiteSpace: 'nowrap',
        border: `1px solid ${on ? 'rgba(105,197,137,.24)' : MM.border}`,
        background: on ? 'rgba(105,197,137,.07)' : 'transparent',
        color: on ? MM.up : MM.dimmer,
      }}
    >
      {label}
    </span>
  );
}

function Stat({ value, unit, caption, tone }: { value: string; unit?: string; caption: string; tone?: string }) {
  return (
    <div style={{ minWidth: 72 }}>
      <div style={{ fontFamily: mono, fontSize: 16, color: tone ?? MM.text, lineHeight: 1.1 }}>
        {value}
        {unit && <span style={{ fontSize: 10, color: MM.dim, marginLeft: 2 }}>{unit}</span>}
      </div>
      <div style={{ fontSize: 9.5, color: MM.dim, marginTop: 3, lineHeight: 1.3 }}>{caption}</div>
    </div>
  );
}

/** What happened last time this pattern fired. The hit rate alone flatters every screen, so
 *  the typical drawdown along the way and the benchmark comparison sit at the same size. */
function CalibrationStrip({ rate }: { rate: ScreenCalibration }) {
  const regime = regimeRead(rate);
  return (
    <div
      style={{
        border: `1px solid ${MM.border}`,
        borderRadius: 7,
        background: MM.panelInset,
        padding: '11px 13px',
        marginBottom: 13,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10, marginBottom: 10 }}>
        <span style={{ font: '600 8.5px var(--mkt-sans)', letterSpacing: '.13em', textTransform: 'uppercase', color: MM.dim }}>
          When this fired before
        </span>
        <span style={{ fontFamily: mono, fontSize: 9.5, color: MM.dimmer }}>
          {sampleWindow(rate)} · {rate.horizonWeeks}w horizon
        </span>
      </div>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '14px 26px' }}>
        <Stat value={rate.pctUp.toFixed(0)} unit="%" caption="resolved up" />
        <Stat
          value={`${rate.medianFwd >= 0 ? '+' : ''}${rate.medianFwd.toFixed(1)}%`}
          caption="median move"
          tone={rate.medianFwd >= 0 ? MM.up : MM.down}
        />
        <Stat value={`${rate.meanMae.toFixed(1)}%`} caption="typical dip along the way" tone={MM.down} />
        <Stat value={rate.pctBeatBench.toFixed(0)} unit="%" caption="beat the index" />
      </div>
      <div style={{ fontSize: 11, color: MM.textSoft, marginTop: 11, lineHeight: 1.5 }}>
        {calibrationRead(rate)}
        {regime && <span style={{ color: MM.faint }}> {regime}</span>}
      </div>
    </div>
  );
}

export function SoftBottomingWatch({ panel, onOpen }: { panel: Panel<SoftBottomItem[]>; onOpen: (s: string) => void }) {
  return (
    <PanelCard
      title="Soft Bottoming Watch"
      status={panel.status}
      right={<span style={{ fontSize: 10, color: MM.dim }}>{panel.data.length} flagged · rare by design</span>}
    >
      <ScreenRule>
        A name well off its high whose weekly decline has stopped getting worse — seven pre-registered
        tests for a base forming, and it takes a majority of them plus a real drawdown to flag.
      </ScreenRule>
      {panel.calibration ? (
        <CalibrationStrip rate={panel.calibration} />
      ) : (
        panel.note && <ScreenRule>{panel.note}</ScreenRule>
      )}
      {panel.data.length === 0 ? (
        <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>
          Nothing flagged right now. That is the normal state — the screen is built to stay quiet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          {panel.data.map((item) => {
            const total = item.testsTotal || item.testsPassed.length;
            return (
              <button
                key={item.symbol}
                onClick={() => onOpen(item.symbol)}
                title={item.name}
                style={{ cursor: 'pointer', padding: '11px 0', borderTop: `1px solid rgba(254,252,244,.05)`, background: 'transparent', border: 'none', borderTopColor: 'rgba(254,252,244,.05)', textAlign: 'left', width: '100%' }}
              >
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
                  <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 600, color: MM.text }}>{item.symbol}</span>
                  {total > 0 && (
                    <span style={{ fontFamily: mono, fontSize: 10.5, color: MM.up }} title={`Bottoming score ${item.score.toFixed(2)} — the share of the screen's tests this name passes`}>
                      {item.testsPassed.length}/{total} tests
                    </span>
                  )}
                  <span style={{ flex: 1 }} />
                  <Reading value={`${item.drawdown} off high`} band={drawdownBand(item.drawdown)} tone={valueTone(item.drawdown)} />
                  <Reading value={`RSI ${item.rsi}`} band={rsiBand(item.rsi)} />
                </div>
                {item.testsPassed.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 7 }}>
                    {item.testsPassed.map((test) => (
                      <Chip key={test} label={SB_TEST_LABELS[test] ?? test} />
                    ))}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      )}
    </PanelCard>
  );
}

export function AccumulationWatch({ panel, onOpen }: { panel: Panel<AccumulationRow[]>; onOpen: (s: string) => void }) {
  const factors = Object.entries(CONFLUENCE_LABELS) as [keyof typeof CONFLUENCE_LABELS, { label: string; rule: string }][];
  return (
    <PanelCard title="Accumulation Watch" status={panel.status} right={<span style={{ fontSize: 10, color: MM.dim }}>ranked by conditions met</span>}>
      <ScreenRule>
        Names already in a pullback, ranked by how many of four conditions they meet:{' '}
        {factors.map(([id, factor], index) => (
          <span key={id}>
            {index > 0 && ', '}
            <span style={{ color: MM.textSoft }} title={factor.rule}>{factor.label}</span>
          </span>
        ))}
        . More conditions is a deeper setup, not a stronger buy.
      </ScreenRule>
      <div className="market-panel-list" style={{ display: 'flex', flexDirection: 'column', maxHeight: 380, overflowY: 'auto', paddingRight: 4 }}>
        {panel.data.map((row) => (
          <button key={row.symbol} onClick={() => onOpen(row.symbol)} style={{ cursor: 'pointer', padding: '10px 0', borderTop: `1px solid rgba(254,252,244,.05)`, background: 'transparent', border: 'none', borderTopColor: 'rgba(254,252,244,.05)', textAlign: 'left', width: '100%' }}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 10 }}>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 9, minWidth: 0 }}>
                <span style={{ fontFamily: mono, fontSize: 13, fontWeight: 600, color: MM.text }}>{row.symbol}</span>
                {row.name !== row.symbol && (
                  <span style={{ fontSize: 11.5, color: MM.muted, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{row.name}</span>
                )}
              </div>
              <span style={{ fontFamily: mono, fontSize: 10, color: row.confluence >= 3 ? MM.accent : MM.dim, whiteSpace: 'nowrap' }}>
                {row.confluence}/4
              </span>
            </div>
            <div style={{ display: 'flex', gap: 14, marginTop: 6 }}>
              <span style={{ fontFamily: mono, fontSize: 10.5, color: valueTone(row.belowMa) }}>
                {row.belowMa} <span style={{ color: MM.dimmer }}>vs 40W</span>
              </span>
              <Reading value={row.drawdown} band={drawdownBand(row.drawdown)} tone={valueTone(row.drawdown)} />
              <Reading value={`RSI ${row.rsi}`} band={rsiBand(row.rsi)} />
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginTop: 7 }}>
              {row.factors.length === 0 ? (
                <span style={{ fontSize: 10.5, color: MM.dimmer, fontStyle: 'italic' }}>in a pullback, no condition met yet</span>
              ) : (
                factors.map(([id, factor]) => (
                  <Chip key={id} label={factor.label} title={factor.rule} on={row.factors.includes(id)} />
                ))
              )}
            </div>
          </button>
        ))}
      </div>
    </PanelCard>
  );
}

export function TrendWatch({ panel, onOpen }: { panel: Panel<TrendRow[]>; onOpen: (s: string) => void }) {
  const [confirmedOnly, setConfirmedOnly] = useState(false);
  const rows = confirmedOnly ? panel.data.filter((row) => row.confirmed) : panel.data;
  // Confirmation only applies to uptrends, so the count is out of the up rows — not out of
  // every row, which made the screen look half-unconfirmed when it was not.
  const upRows = panel.data.filter((row) => row.direction === 'up');
  const confirmed = upRows.filter((row) => row.confirmed).length;

  return (
    <PanelCard
      title="Trend-Change Watch"
      status={panel.status}
      right={
        <button
          type="button"
          onClick={() => setConfirmedOnly((value) => !value)}
          title="A trend is confirmed once price also holds above its 10-week average"
          style={{ cursor: 'pointer', border: `1px solid ${confirmedOnly ? 'rgba(251,148,35,.3)' : MM.border}`, background: 'transparent', color: confirmedOnly ? MM.accent : MM.dim, borderRadius: 6, padding: '3px 8px', font: '600 9px var(--mkt-sans)', letterSpacing: '.08em', textTransform: 'uppercase' }}
        >
          confirmed only · {confirmed}/{upRows.length}
        </button>
      }
    >
      <ScreenRule>
        Which side of its weekly moving-average stack each name sits on, and how long it has held
        there. {upRows.length} of {panel.data.length} are on the up side, {confirmed} of those
        confirmed by price holding above its 10-week average.
      </ScreenRule>
      <div className="market-panel-list" style={{ display: 'flex', flexDirection: 'column', maxHeight: 320, overflowY: 'auto', paddingRight: 4 }}>
        {rows.length === 0 ? (
          <div style={{ fontSize: 11.5, color: MM.dim, fontStyle: 'italic' }}>No name in this screen is confirmed right now.</div>
        ) : (
          rows.map((row) => {
            const isUp = row.direction === 'up';
            return (
              <button key={row.symbol} onClick={() => onOpen(row.symbol)} style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 11, padding: '9px 0', borderTop: `1px solid rgba(254,252,244,.05)`, background: 'transparent', border: 'none', borderTopColor: 'rgba(254,252,244,.05)', textAlign: 'left', width: '100%' }}>
                <span style={{ width: 20, height: 20, borderRadius: 5, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, flex: '0 0 auto', background: isUp ? 'rgba(105,197,137,.12)' : 'rgba(217,109,95,.12)', color: isUp ? MM.up : MM.down }}>
                  {isUp ? '↑' : '↓'}
                </span>
                <span style={{ fontFamily: mono, fontSize: 12.5, fontWeight: 600, color: MM.text, width: 46, flex: '0 0 auto' }}>{row.symbol}</span>
                <span style={{ flex: 1, minWidth: 0, fontFamily: mono, fontSize: 11, color: valueTone(row.belowMa) }}>
                  {row.belowMa} <span style={{ color: MM.dimmer }}>vs 40W</span>
                </span>
                <span style={{ fontFamily: mono, fontSize: 10, color: MM.dim, flex: '0 0 auto' }} title="How long price has held this side of the stack">
                  {trendAge(row.weeksInTrend)}
                </span>
                <span
                  title={
                    !isUp
                      ? 'Confirmation is an uptrend test — it does not apply to a name below its stack'
                      : row.confirmed
                        ? 'Price is also holding above its 10-week average'
                        : 'Above the 40-week anchor, but not holding above its 10-week average'
                  }
                  style={{ fontFamily: mono, fontSize: 9, width: 62, textAlign: 'right', flex: '0 0 auto', color: row.confirmed ? MM.up : MM.dimmer }}
                >
                  {!isUp ? '—' : row.confirmed ? 'confirmed' : 'unconfirmed'}
                </span>
              </button>
            );
          })
        )}
      </div>
    </PanelCard>
  );
}
