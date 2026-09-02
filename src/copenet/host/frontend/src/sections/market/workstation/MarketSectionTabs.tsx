// The section strip: one flat row of destinations, each a route.
//
// Tabs double as an inbox — a neutral count says the last sweep delivered something into a
// section since the operator last opened it, and a red badge says the section's data failed.
// Both survive on every screen width because the strip is chrome.

import type { ReactNode } from 'react';
import type { MarketSection } from '../../../lib/appSectionRouting';

export function MarketSectionTabs({
  tabs,
  active,
  onSelect,
  newCounts,
  warnings,
  tools,
}: {
  tabs: { id: MarketSection; label: string; hint: string }[];
  active: MarketSection;
  onSelect: (section: MarketSection) => void;
  newCounts: Partial<Record<MarketSection, number>>;
  warnings: Partial<Record<MarketSection, number>>;
  tools?: ReactNode;
}) {
  return (
    <div className="mw-tabs" role="tablist" aria-label="Market sections">
      {tabs.map((tab, index) => {
        const fresh = newCounts[tab.id] ?? 0;
        const broken = warnings[tab.id] ?? 0;
        const shortcut = index < 9 && tab.id !== 'watchlist' ? ` (${index + 1})` : '';
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            className="tw-tab"
            aria-selected={active === tab.id}
            title={`${tab.hint}${shortcut}`}
            onClick={() => onSelect(tab.id)}
          >
            {tab.label}
            {broken > 0 && <span className="tw-tab__badge" title={`${broken} source${broken === 1 ? '' : 's'} unavailable`}>{broken}</span>}
            {broken === 0 && fresh > 0 && <span className="mw-tab__new" title={`${fresh} new since you last opened ${tab.label}`}>{fresh}</span>}
          </button>
        );
      })}
      <span className="mw-tabs__spacer" />
      {tools && <div className="mw-tabs__tools">{tools}</div>}
    </div>
  );
}
