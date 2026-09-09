// The morning card: who you are, what the market is, and what changed.
//
// The one panel that must be readable in three seconds. Regime and the macro strip come
// from the same dashboard panels the market bar reads, so Home and Market can never
// disagree about the state of the tape; "what matters" is the brief's own ranking, not a
// second opinion computed here.

import { useMemo } from 'react';
import { ArrowUpRight } from 'lucide-react';
import { composeMatters } from '../../../sections/market/marketBriefModel';
import { toneColor } from '../../../sections/market/marketUi';
import { Sparkline } from '../../../sections/market/workspaceViz';
import type { DashboardPayload, MorningBriefPayload } from '../../../sections/market/types';
import type { MarketClock } from '../deskModel';

const REGIME_COLORS: Record<string, string> = {
  'risk-off': 'var(--mkt-down)',
  chop: 'var(--mkt-muted)',
  'risk-on': 'var(--mkt-up)',
  'event-risk': 'var(--mkt-accent)',
};

const REGIME_LABELS: Record<string, string> = {
  'risk-off': 'Risk-off',
  chop: 'Chop',
  'risk-on': 'Risk-on',
  'event-risk': 'Event risk',
};

/** The macro panel carries twelve readings in rates → credit → volatility → FX →
 *  commodities → crypto order. The strip has room for four beside the regime, and taking
 *  the first four would show three flavours of duration and nothing else. These are the
 *  four that answer "what kind of day is it" — anything missing from the panel is skipped
 *  rather than back-filled, so the strip never pads itself with whatever was next. */
const STRIP_PREFERENCE = ['VIX', 'TNX', 'DXY', 'BTCUSD'];
const STRIP_SLOTS = 4;
const MATTERS_ON_HOME = 3;

function greeting(hour: number): string {
  if (hour < 5) return 'Still up';
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

export function BriefingCard({
  dashboard,
  brief,
  clock,
  quote,
  onOpenMarket,
}: {
  dashboard: DashboardPayload | null;
  brief: MorningBriefPayload | null;
  clock: MarketClock;
  /** From the desk snapshot, not the market read, so it renders on a cold market cache. */
  quote: { text: string; attribution: string } | null;
  onOpenMarket: (view: 'briefing' | 'evidence' | 'signals') => void;
}) {
  const regime = dashboard?.regime.data.current ?? '';
  const macro = useMemo(() => {
    const rows = dashboard?.macro.data ?? [];
    const byLabel = new Map(rows.map((row) => [row.label.toUpperCase(), row]));
    return STRIP_PREFERENCE.map((label) => byLabel.get(label)).filter((row) => row != null).slice(0, STRIP_SLOTS);
  }, [dashboard?.macro.data]);
  const matters = brief ? composeMatters(brief).slice(0, MATTERS_ON_HOME) : [];
  const summary = dashboard?.briefing.data.summary ?? '';
  const quoteHost = dashboard === null && brief === null;

  return (
    <section className="hd-card hd-span-8">
      <div className="hd-brief">
        <div className="hd-brief__greet">
          <div className="min-w-0">
            <h1 className="hd-brief__hello">{greeting(new Date().getHours())}, Operator.</h1>
            <p className="hd-brief__sub">
              {quoteHost
                ? 'No market read stored yet — run a sweep from the Market workstation.'
                : "Here's what's moving the market — and your system."}
            </p>
          </div>
          <div className="hd-brief__stamp">
            <b>{new Date().toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' })}</b>
            <span>{clock.time}</span>
          </div>
        </div>

        <div className="hd-strip">
          <div className="hd-strip__cell">
            <div className="hd-strip__label">Market regime</div>
            <div className="hd-regime" style={{ color: REGIME_COLORS[regime] ?? 'var(--mkt-dim)' }}>
              <span className="hd-regime__dot" />
              <span className="hd-regime__label">{REGIME_LABELS[regime] ?? 'No read'}</span>
            </div>
            {summary && <div className="hd-regime__note">{summary}</div>}
          </div>

          {macro.map((item) => (
            <div key={item.label} className="hd-strip__cell">
              <div className="hd-strip__label">{item.label}</div>
              <div className="hd-strip__value">{item.value}</div>
              <div className="hd-strip__change" style={{ color: toneColor(item.tone) }}>
                {item.change}
              </div>
              <span className="hd-strip__spark">
                {item.spark.length > 1 && <Sparkline points={item.spark} color={toneColor(item.tone)} height={26} />}
              </span>
            </div>
          ))}
        </div>

        <div className="hd-brief__foot">
          <div className="hd-matters">
            <div className="hd-matters__title">What matters today</div>
            {matters.length === 0 ? (
              <div className="hd-matter__text">Nothing new since the last sweep.</div>
            ) : (
              matters.map((matter) => (
                <button
                  key={matter.key}
                  type="button"
                  className="hd-matter"
                  onClick={() => onOpenMarket(matter.source === 'signal flip' ? 'signals' : 'evidence')}
                  title={`${matter.kind} · ${matter.source}`}
                >
                  <span className="hd-matter__dot" style={{ background: toneColor(matter.tone) }} />
                  <span className="hd-matter__sym">{matter.symbol}</span>
                  <span className="hd-matter__text">{matter.text}</span>
                </button>
              ))
            )}
            {brief?.headline && (
              <button type="button" className="hd-link" style={{ alignSelf: 'flex-start', marginTop: 2 }} onClick={() => onOpenMarket('briefing')}>
                Full read <ArrowUpRight size={10} />
              </button>
            )}
          </div>

          {quote && (
            <figure className="hd-quote">
              <blockquote className="hd-quote__text">"{quote.text}"</blockquote>
              <figcaption className="hd-quote__by">— {quote.attribution}</figcaption>
            </figure>
          )}
        </div>
      </div>
    </section>
  );
}
