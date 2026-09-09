// Market Pulse: the tape, tabbed by the operator's own watchlists.
//
// Tabs follow `watchlist.lists` rather than a fixed set of asset classes, so a screener that
// writes ten to fifteen names into a list each morning shows up here with no code change.
// The Macro tab is appended because it comes from the dashboard, not from anything curated.

import { useEffect, useMemo, useState } from 'react';
import { Radio } from 'lucide-react';
import { toneColor } from '../../../sections/market/marketUi';
import { Sparkline } from '../../../sections/market/workspaceViz';
import type { MacroItem } from '../../../sections/market/types';
import type { MarketWatchlistState } from '../../../sections/market/useMarketMonitorData';
import { buildPulseTabs, pulseRows } from '../deskModel';
import { Card } from './Card';

export function MarketPulse({
  watchlist,
  macro,
  onOpenTicker,
}: {
  watchlist: MarketWatchlistState;
  macro: MacroItem[];
  onOpenTicker: (symbol: string) => void;
}) {
  const tabs = useMemo(() => buildPulseTabs(watchlist.lists), [watchlist.lists]);
  const [activeId, setActiveId] = useState<string | null>(null);

  // The default tab is whichever list the operator last selected in Market — the two
  // surfaces should agree about which list is "the" list.
  const active = useMemo(
    () => tabs.find((tab) => tab.id === activeId) ?? tabs.find((tab) => tab.label === watchlist.active) ?? tabs[0],
    [activeId, tabs, watchlist.active],
  );

  // Selecting another of the operator's lists loads it, which is what makes the tab strip
  // real rather than decorative — the rows come from the watchlist RPC, not from a filter.
  useEffect(() => {
    if (active && active.kind === 'watchlist' && active.label !== watchlist.active) {
      void watchlist.selectList(active.label);
    }
  }, [active, watchlist]);

  const rows = useMemo(() => (active ? pulseRows(active, watchlist.items, macro) : []), [active, macro, watchlist.items]);

  return (
    <Card
      title="Market pulse"
      icon={Radio}
      span={7}
      head={
        <>
          <div className="hd-card__spacer" />
          <span className="hd-saved">{rows.length ? `${rows.length} names` : ''}</span>
        </>
      }
    >
      {/* The tab strip gets its own row rather than sharing the header: this operator has
          twenty watchlists, and a strip that scrolls inside a 34px header beside a title is
          unreadable at the exact moment it matters most. */}
      <div className="hd-tabs" role="tablist" aria-label="Market pulse lists">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active?.id === tab.id}
            className="hd-tab"
            onClick={() => setActiveId(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      {rows.length === 0 ? (
        <div className="hd-empty">
          {watchlist.loading ? 'Loading…' : 'This list is empty. Add names from the Market workstation.'}
        </div>
      ) : (
        <div className="hd-pulse-grid">
          {rows.map((row) => (
            <button
              key={row.symbol}
              type="button"
              className="hd-pulse"
              data-navigable={row.navigable}
              disabled={!row.navigable}
              onClick={() => row.navigable && onOpenTicker(row.symbol)}
              title={row.name}
            >
              <div className="hd-pulse__sym">{row.symbol}</div>
              <div className="hd-pulse__value">{row.value}</div>
              <div className="hd-pulse__change" style={{ color: toneColor(row.tone) }}>
                {row.change}
              </div>
              <span className="hd-pulse__spark">
                {row.spark.length > 1 && <Sparkline points={row.spark} color={toneColor(row.tone)} height={30} />}
              </span>
            </button>
          ))}
        </div>
      )}
    </Card>
  );
}
