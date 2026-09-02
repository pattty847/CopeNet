// Structure — rates and relative rotation, at full workspace height.

import { useMemo } from 'react';
import { Rrg } from '../RrgChart';
import { TreasuryYieldCurve } from '../TreasuryYieldCurve';
import { ArrangeMenu, SectionGrid, SectionHeader, useSectionLayout, type SectionPanel } from './SectionGrid';
import type { DashboardPayload, MarketRead } from '../types';

export function StructureSection({
  dashboard,
  read,
  onOpen,
  isMobile,
}: {
  dashboard: DashboardPayload;
  read: MarketRead | null;
  onOpen: (symbol: string) => void;
  isMobile: boolean;
}) {
  const panels = useMemo<SectionPanel[]>(
    () => [
      { id: 'treasury', title: 'Treasury curve', defaultWidth: 'full', canHalf: false, node: <TreasuryYieldCurve /> },
      { id: 'sectorRrg', title: 'Sector rotation', defaultWidth: 'full', canHalf: true, node: <Rrg panel={dashboard.rrg} onOpen={onOpen} note={read?.rotationRead} /> },
      {
        id: 'industryRrg',
        title: 'Industry rotation',
        defaultWidth: 'full',
        canHalf: true,
        node: <Rrg panel={dashboard.industryRrg} onOpen={onOpen} title="Industry Rotation · RRG" subtitle="Regional banks, biotech, retail, homebuilders, defense vs S&P 500 · weekly" />,
      },
    ],
    [dashboard.industryRrg, dashboard.rrg, onOpen, read?.rotationRead],
  );
  const layout = useSectionLayout('structure', panels);

  return (
    <>
      <SectionHeader label="Structure" meta="rates and relative rotation · weekly">
        {!isMobile && <ArrangeMenu layout={layout} />}
      </SectionHeader>
      <SectionGrid layout={layout} isMobile={isMobile} />
    </>
  );
}
