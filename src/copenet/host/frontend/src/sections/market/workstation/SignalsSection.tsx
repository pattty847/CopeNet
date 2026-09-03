// Signals — the canonical home for every screen's full list. The briefing shows only what
// changed (as Matters) and what is currently flagged by the rare calibrated screen.

import { useMemo } from 'react';
import { AccumulationWatch, SoftBottomingWatch, TrendWatch } from '../panelsLists';
import { ArrangeMenu, SectionGrid, SectionHeader, useSectionLayout, type SectionPanel } from './SectionGrid';
import type { DashboardPayload } from '../types';

export function SignalsSection({ dashboard, onOpen, isMobile }: { dashboard: DashboardPayload; onOpen: (symbol: string) => void; isMobile: boolean }) {
  const panels = useMemo<SectionPanel[]>(
    () => [
      { id: 'softBottoming', title: 'Soft bottoming watch', defaultWidth: 'full', canHalf: true, node: <SoftBottomingWatch panel={dashboard.softBottoming} onOpen={onOpen} /> },
      { id: 'accumulation', title: 'Accumulation watch', defaultWidth: 'half', canHalf: true, node: <AccumulationWatch panel={dashboard.accumulation} onOpen={onOpen} /> },
      { id: 'trend', title: 'Trend-change watch', defaultWidth: 'half', canHalf: true, node: <TrendWatch panel={dashboard.trend} onOpen={onOpen} /> },
    ],
    [dashboard.accumulation, dashboard.softBottoming, dashboard.trend, onOpen],
  );
  const layout = useSectionLayout('signals', panels, isMobile);
  const flagged = dashboard.softBottoming.data.length + dashboard.trend.data.length + dashboard.accumulation.data.length;

  return (
    <>
      <SectionHeader label="Signals" meta={`${flagged} names across three screens`}>
        {!isMobile && <ArrangeMenu layout={layout} />}
      </SectionHeader>
      <SectionGrid layout={layout} isMobile={isMobile} />
    </>
  );
}
