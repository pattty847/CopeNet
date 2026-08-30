// The bottom dock.
//
// This is the structural bet: the chart and the research it explains share ONE vertical axis
// with snap presets, so moving between "look at the price" and "read the evidence" is a
// keypress, never a scroll to somewhere the chart no longer exists. Heights are remembered
// per tab because Fundamentals small multiples need room Overview would only waste.

import type { ReactNode } from 'react';
import { Rows2 } from 'lucide-react';
import { RESEARCH_TABS, nextSnap, type DrawerSnap, type ResearchTab } from './tickerWorkspaceState';
import './financialResearch.css';

export function ResearchDrawer({
  tab,
  onTab,
  tabs,
  snap,
  onSnap,
  warnings,
  children,
}: {
  tab: ResearchTab;
  onTab: (tab: ResearchTab) => void;
  /** Tabs that can show something real for this asset — a fund has no issuer filings. */
  tabs: ResearchTab[];
  snap: DrawerSnap;
  onSnap: (snap: DrawerSnap) => void;
  /** Per-tab problem counts. These must survive the collapsed drawer, or a workspace with a
   *  failed SEC pull and a healthy one look identical. */
  warnings: Partial<Record<ResearchTab, number>>;
  children: ReactNode;
}) {
  return (
    <section className="tw-drawer" data-snap={snap} aria-label="Research">
      <div className="tw-drawer__tabs" role="tablist">
        {RESEARCH_TABS.filter((entry) => tabs.includes(entry.id)).map((entry) => {
          const count = warnings[entry.id] ?? 0;
          return (
            <button
              key={entry.id}
              type="button"
              role="tab"
              className="tw-tab"
              aria-selected={tab === entry.id && snap !== 'collapsed'}
              onClick={() => {
                if (tab === entry.id && snap !== 'collapsed') onSnap('collapsed');
                else {
                  onTab(entry.id);
                  if (snap === 'collapsed') onSnap('half');
                }
              }}
            >
              {entry.label}
              {count > 0 && <span className="tw-tab__badge" title={`${count} item${count === 1 ? '' : 's'} need attention`}>{count}</span>}
            </button>
          );
        })}
        <span style={{ flex: 1 }} />
        <button
          type="button"
          className="tw-iconbtn"
          onClick={() => onSnap(nextSnap(snap))}
          title={`Drawer height: ${snap} — press \\ to cycle`}
          aria-label="Cycle drawer height"
        >
          <Rows2 size={14} />
        </button>
      </div>
      {snap !== 'collapsed' && (
        <div className="tw-drawer__panel" role="tabpanel">{children}</div>
      )}
    </section>
  );
}
