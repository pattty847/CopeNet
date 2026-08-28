import { useRef, type KeyboardEvent } from 'react';
import { TickerEvidencePanel } from './TickerEvidencePanel';
import { TickerFundamentalsPanel } from './TickerFundamentalsPanel';
import { TickerOverviewPanel } from './TickerOverviewPanel';
import { TickerReadPanel } from './TickerReadPanel';
import type { TickerDetailPayload, EvidenceItem } from './types';
import type { TickerEvidenceState } from './useMarketMonitorData';
import type { TickerResearchTab } from './TickerContextStrip';

const TABS: Array<{ id: TickerResearchTab; label: string }> = [
  { id: 'overview', label: 'Overview' },
  { id: 'fundamentals', label: 'Fundamentals' },
  { id: 'evidence', label: 'SEC & Events' },
  { id: 'synthesis', label: 'Synthesis' },
];

export function TickerResearchDock({
  activeTab,
  detail,
  evidence,
  evidenceState,
  onTab,
}: {
  activeTab: TickerResearchTab;
  detail: TickerDetailPayload;
  evidence: EvidenceItem[];
  evidenceState: TickerEvidenceState;
  onTab: (tab: TickerResearchTab) => void;
}) {
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = TABS.findIndex((tab) => tab.id === activeTab);
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight' && event.key !== 'Home' && event.key !== 'End') return;
    event.preventDefault();
    const nextIndex = event.key === 'Home' ? 0 : event.key === 'End' ? TABS.length - 1 : (currentIndex + (event.key === 'ArrowRight' ? 1 : -1) + TABS.length) % TABS.length;
    onTab(TABS[nextIndex].id);
    tabRefs.current[nextIndex]?.focus();
  };

  return (
    <section className="ticker-research-dock" aria-label="Asset research">
      <div className="ticker-research-tabs" role="tablist" aria-label="Research views" onKeyDown={onKeyDown}>
        {TABS.map((tab, index) => (
          <button
            key={tab.id}
            ref={(node) => { tabRefs.current[index] = node; }}
            type="button"
            role="tab"
            id={`ticker-tab-${tab.id}`}
            aria-controls={`ticker-panel-${tab.id}`}
            aria-selected={activeTab === tab.id}
            tabIndex={activeTab === tab.id ? 0 : -1}
            onClick={() => onTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div id="ticker-panel-overview" role="tabpanel" aria-labelledby="ticker-tab-overview" hidden={activeTab !== 'overview'}>
        <TickerOverviewPanel detail={detail} evidence={evidence} />
      </div>
      <div id="ticker-panel-fundamentals" role="tabpanel" aria-labelledby="ticker-tab-fundamentals" hidden={activeTab !== 'fundamentals'}>
        <TickerFundamentalsPanel symbol={detail.symbol} active={activeTab === 'fundamentals'} />
      </div>
      <div id="ticker-panel-evidence" role="tabpanel" aria-labelledby="ticker-tab-evidence" hidden={activeTab !== 'evidence'}>
        <TickerEvidencePanel state={evidenceState} />
      </div>
      <div id="ticker-panel-synthesis" role="tabpanel" aria-labelledby="ticker-tab-synthesis" hidden={activeTab !== 'synthesis'}>
        <TickerReadPanel symbol={detail.symbol} />
      </div>
    </section>
  );
}
