// "Since you last looked" — the cockpit's anchor.
//
// The market page's first question is not "what is the market" but "what changed while I
// was away", so the delta owns the stage the way the chart owns the ticker workspace.
// Every row answers a standing question — REGIME, MATTERS, MOVERS, BOOK, NEXT 7D, LEDGER —
// and renders only deltas; the standing picture lives in the tape column and the dock.
// Beneath a seam, SYNTHESIS carries the model's read, visibly stamped as interpretation.
// Honest empty states throughout: a quiet day says so instead of manufacturing news.

import { useState } from 'react';
import { RefreshCw, Sparkles } from 'lucide-react';
import { ModelBadge, toneColor } from './marketUi';
import type { BriefMover, MarketRead, MorningBriefPayload, Panel, Regime, Tone } from './types';
import type { ReactNode } from 'react';

const MATTERS_VISIBLE = 4;

const REGIME_COLOR: Record<string, string> = {
  'risk-on': 'var(--mkt-up)',
  'risk-off': 'var(--mkt-down)',
  chop: 'var(--mkt-muted)',
  'event-risk': 'var(--mkt-accent)',
};

interface MatterItem {
  key: string;
  kind: string;
  symbol: string;
  text: string;
  tone: Tone;
  t?: number | null;
  url?: string | null;
}

/** Rank what changed by how much it should interrupt a glance: flagged SEC evidence
 *  (clusters, high-signal 8-Ks) > signal flips > rotation moves > the rest. */
export function composeMatters(brief: MorningBriefPayload): MatterItem[] {
  const items: MatterItem[] = [];
  const flagged = brief.newEvidence.filter((entry) => entry.flag);
  const plain = brief.newEvidence.filter((entry) => !entry.flag);
  flagged.forEach((entry, index) =>
    items.push({ key: `evf-${index}`, kind: entry.type, symbol: entry.symbol, text: entry.headline, tone: entry.tone, t: entry.t, url: entry.url }),
  );
  brief.signalFlips.forEach((flip, index) =>
    items.push({ key: `flip-${index}`, kind: flip.kind, symbol: flip.symbol, text: flip.detail, tone: flip.tone }),
  );
  brief.rrgShifts.forEach((shift, index) =>
    items.push({ key: `rrg-${index}`, kind: 'rotation', symbol: shift.symbol, text: `${shift.fromQuadrant} → ${shift.toQuadrant}`, tone: shift.tone }),
  );
  plain.forEach((entry, index) =>
    items.push({ key: `ev-${index}`, kind: entry.type, symbol: entry.symbol, text: entry.headline, tone: entry.tone, t: entry.t, url: entry.url }),
  );
  return items;
}

function sweptStamp(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], { weekday: 'short', hour: 'numeric', minute: '2-digit' });
}

function matterDate(t?: number | null): string {
  if (!t || !Number.isFinite(t)) return '';
  const parsed = new Date(t * 1000);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString([], { month: 'short', day: 'numeric', timeZone: 'UTC' });
}

function BriefRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mc-row">
      <span className="mc-row__label">{label}</span>
      <div className="mc-row__body">{children}</div>
    </div>
  );
}

/** Headline with its emphasis substring lifted into the accent, when the two align. */
function Emphasized({ text, emphasis }: { text: string; emphasis?: string }) {
  if (!emphasis || !text.includes(emphasis)) return <>{text}</>;
  const [before, after] = text.split(emphasis);
  return (
    <>
      {before}
      <em>{emphasis}</em>
      {after}
    </>
  );
}

export function BriefColumn({
  brief,
  generating,
  onRunNow,
  regime,
  regimeReasoningAvailable,
  read,
  reading,
  readError,
  onRunRead,
  onExplain,
  onOpen,
  calendar,
  ledgerLine,
  onOpenLedger,
}: {
  brief: MorningBriefPayload | null;
  generating: boolean;
  onRunNow: () => void;
  regime?: Panel<Regime>;
  regimeReasoningAvailable: boolean;
  read: MarketRead | null;
  reading: boolean;
  readError: string | null;
  onRunRead: () => void;
  onExplain: () => void;
  onOpen: (symbol: string) => void;
  calendar?: ReactNode;
  ledgerLine: string | null;
  onOpenLedger: () => void;
}) {
  const [allMatters, setAllMatters] = useState(false);
  const matters = brief ? composeMatters(brief) : [];
  const visibleMatters = allMatters ? matters : matters.slice(0, MATTERS_VISIBLE);
  const hiddenCount = matters.length - MATTERS_VISIBLE;
  const regimeCurrent = regime?.data?.current;
  const movers: BriefMover[] = brief?.movers ?? [];

  return (
    <section className="mc-brief" aria-label="Since you last looked">
      <div className="mc-sect">
        <span className="mc-sect__label">Since you last looked</span>
        {brief && <span className="mc-sect__meta">swept {sweptStamp(brief.generatedAt)}</span>}
        <span className="mc-sect__spacer" />
        <button type="button" className="tw-btn" onClick={onRunNow} disabled={generating}>
          {generating ? <RefreshCw size={12} className="tw-spin" /> : <RefreshCw size={12} />}
          {generating ? 'Sweeping…' : 'Sweep'}
        </button>
      </div>

      {brief ? (
        <h1 className="mc-headline">{brief.headline}</h1>
      ) : (
        <p className="mc-quiet" style={{ margin: '2px 0 12px' }}>
          {generating
            ? 'First pre-market sweep is running — refreshing every symbol, diffing SEC filings and signals…'
            : 'No morning brief yet. The sentinel sweeps pre-market every day and reports what changed overnight.'}
        </p>
      )}
      {brief?.note && <p className="mc-quiet" style={{ margin: '0 0 10px', fontStyle: 'italic' }}>{brief.note}</p>}

      {regimeCurrent && (
        <BriefRow label="Regime">
          <span style={{ fontFamily: 'var(--mkt-mono)', fontSize: 'var(--mkt-t-value)', color: REGIME_COLOR[regimeCurrent] ?? 'var(--mkt-soft)' }}>
            {brief?.regimeShift ? `${brief.regimeShift.from} → ${brief.regimeShift.to} today` : `${regimeCurrent} — unchanged since last sweep`}
          </span>
          {regimeReasoningAvailable && (
            <button type="button" className="mc-more" style={{ marginLeft: 8 }} onClick={onExplain}>
              why →
            </button>
          )}
        </BriefRow>
      )}

      {brief && (
        <BriefRow label="Matters">
          {matters.length === 0 ? (
            <span className="mc-quiet" style={{ fontStyle: 'italic' }}>
              Nothing thesis-relevant — no new filings, signal flips, or rotation moves.
            </span>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              {visibleMatters.map((matter) => (
                <button key={matter.key} type="button" className="mc-matter" onClick={() => onOpen(matter.symbol)}>
                  <span className="mc-matter__kind">{matter.kind}</span>
                  <span className="mc-matter__sym">{matter.symbol}</span>
                  <span className="mc-matter__text" style={{ color: matter.tone === 'flat' ? undefined : toneColor(matter.tone) }}>{matter.text}</span>
                  {matter.url ? (
                    <a
                      href={matter.url}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(event) => event.stopPropagation()}
                      className="mc-matter__when"
                      style={{ color: 'var(--mkt-accent)', textDecoration: 'none' }}
                    >
                      filing ↗
                    </a>
                  ) : (
                    matterDate(matter.t) && <span className="mc-matter__when">{matterDate(matter.t)}</span>
                  )}
                </button>
              ))}
              {hiddenCount > 0 && (
                <button type="button" className="mc-more" onClick={() => setAllMatters((value) => !value)}>
                  {allMatters ? '▴ show top 4' : `▾ ${hiddenCount} more`}
                </button>
              )}
            </div>
          )}
        </BriefRow>
      )}

      {movers.length > 0 && (
        <BriefRow label="Movers">
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 5 }}>
            {movers.map((mover, index) => (
              <button key={`mv-${index}`} type="button" className="mc-mover" onClick={() => onOpen(mover.symbol)} title={mover.name}>
                <span>{mover.symbol}</span>
                <span style={{ color: toneColor(mover.tone) }}>
                  {mover.changePct > 0 ? '+' : ''}
                  {mover.changePct.toFixed(1)}%
                </span>
              </button>
            ))}
            <span className="mc-matter__when">{brief?.moversLabel || 'last session'}</span>
          </div>
        </BriefRow>
      )}

      {brief?.portfolioNote && (
        <BriefRow label="Book">
          <span style={{ fontSize: 'var(--mkt-t-value)', color: 'var(--mkt-muted)' }}>{brief.portfolioNote}</span>
        </BriefRow>
      )}

      {calendar && <BriefRow label="Next 7d">{calendar}</BriefRow>}

      {ledgerLine && (
        <BriefRow label="Ledger">
          <span style={{ fontFamily: 'var(--mkt-mono)', fontSize: 'var(--mkt-t-value)', color: 'var(--mkt-muted)' }}>{ledgerLine}</span>
          <button type="button" className="mc-more" style={{ marginLeft: 8 }} onClick={onOpenLedger}>
            open →
          </button>
        </BriefRow>
      )}

      <div className="mc-synth">
        <div className="mc-sect" style={{ marginBottom: 4 }}>
          <span className="mc-sect__label">Synthesis</span>
          {read && <ModelBadge model={read.model} generatedAt={read.generatedAt} />}
          <span className="mc-sect__spacer" />
          <button type="button" className="tw-btn" style={{ color: 'var(--mkt-info)', borderColor: 'rgba(143,184,232,.3)' }} onClick={onRunRead} disabled={reading}>
            {reading ? <RefreshCw size={12} className="tw-spin" /> : <Sparkles size={12} />}
            {reading ? 'Reading the tape…' : read ? 'Read again' : 'Model read'}
          </button>
        </div>

        {readError && <p className="mc-quiet" role="alert" style={{ color: 'var(--mkt-down)', margin: '4px 0 8px' }}>{readError}</p>}

        {read ? (
          <>
            <p style={{ margin: '6px 0 0', font: '600 15px Inter', lineHeight: 1.45, color: 'var(--mkt-text)', maxWidth: '62ch' }}>
              <Emphasized text={read.headline} emphasis={read.emphasis} />
            </p>
            <p className="mc-synth__summary">{read.summary}</p>
            {read.attention.length > 0 && (
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {read.attention.map((item, index) => (
                  <button key={`attn-${index}`} type="button" className="mc-attn" onClick={() => onOpen(item.symbol)} title={item.why}>
                    <span className="mc-attn__sym">{item.symbol}</span>
                    <span className="mc-attn__kind">{item.kind}</span>
                  </button>
                ))}
              </div>
            )}
            <button type="button" className="mc-more" style={{ marginTop: 8 }} onClick={onExplain}>
              Why this read →
            </button>
            {read.caveats && <p className="mc-caveat">{read.caveats}</p>}
          </>
        ) : (
          !readError && (
            <p className="mc-quiet" style={{ margin: '4px 0 0' }}>
              No model read yet. A read interprets the computed facts — regime, rotation, attention — and logs every call to the forward ledger. Evidence-based with caveats, never forecasts.
            </p>
          )
        )}
      </div>
    </section>
  );
}
