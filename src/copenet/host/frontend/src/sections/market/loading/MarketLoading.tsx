import type { MarketSection } from '../../../lib/appSectionRouting';
import { loadSectionLayout, resolveSectionLayout, type SectionPanelSpec } from '../marketWorkstationState';
import { PORTFOLIO_PANELS, SIGNAL_PANELS, STRUCTURE_PANELS } from '../marketSectionPanels';
import { SkeletonPanel, WorkspaceLoading } from './WorkspaceLoading';

export function MarketLoading({ section, isMobile }: { section: MarketSection; isMobile: boolean }) {
  const specs: SectionPanelSpec[] =
    section === 'structure'
      ? Object.values(STRUCTURE_PANELS)
      : section === 'signals'
        ? Object.values(SIGNAL_PANELS)
        : section === 'portfolio'
          ? Object.values(PORTFOLIO_PANELS)
          : [];
  const panels = resolveSectionLayout(specs, loadSectionLayout(section), isMobile).filter((panel) => !panel.hidden);
  return (
    <WorkspaceLoading label="Loading market workspace…">
      {section === 'briefing' ? (
        <div className="workspace-loading__brief">
          <SkeletonPanel />
          <SkeletonPanel kind="chart" />
          <SkeletonPanel />
        </div>
      ) : specs.length ? (
        <div className="mw-grid">
          {panels.map((panel) => (
            <div key={panel.spec.id} data-panel={panel.spec.id} data-width={panel.width}>
              <SkeletonPanel kind={section === 'structure' ? 'chart' : 'rows'} />
            </div>
          ))}
        </div>
      ) : (
        <SkeletonPanel />
      )}
    </WorkspaceLoading>
  );
}
