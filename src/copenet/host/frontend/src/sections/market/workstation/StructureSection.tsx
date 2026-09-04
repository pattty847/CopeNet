// Structure — rates and relative rotation, at full workspace height.

import { useMemo } from 'react';
import { STRUCTURE_PANELS } from '../marketSectionPanels';
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
      { ...STRUCTURE_PANELS.treasury, node: <TreasuryYieldCurve /> },
      { ...STRUCTURE_PANELS.sectorRrg, node: <Rrg panel={dashboard.rrg} onOpen={onOpen} note={read?.rotationRead} /> },
      {
        ...STRUCTURE_PANELS.industryRrg,
        node: <Rrg panel={dashboard.industryRrg} onOpen={onOpen} title="Industry Rotation · RRG" subtitle="Regional banks, biotech, retail, homebuilders, defense vs S&P 500 · weekly" />,
      },
    ],
    [dashboard.industryRrg, dashboard.rrg, onOpen, read?.rotationRead],
  );
  const layout = useSectionLayout('structure', panels, isMobile);

  return (
    <>
      <SectionHeader label="Structure" meta="rates and relative rotation · weekly">
        {!isMobile && <ArrangeMenu layout={layout} />}
      </SectionHeader>
      <SectionGrid layout={layout} isMobile={isMobile} />
    </>
  );
}
