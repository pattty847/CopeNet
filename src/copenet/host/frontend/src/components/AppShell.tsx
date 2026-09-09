import { useEffect } from 'react';
import { wsClient } from '../lib/wsClient';
import { useAppStore } from '../store/useAppStore';
import { AgentsPage } from './AgentsPage';
import { CommandPalette } from './CommandPalette';
import { ConnectionBanner } from './ConnectionBanner';
import { DataToolsPage } from './DataToolsPage';
import { ExperimentsPage } from './ExperimentsPage';
import { HomePage } from './HomePage';
import { MarketMonitor } from '../sections/market/MarketMonitor';
import { MobileBottomNav, MobileTopBar } from './mobile/MobileNav';
import { ObservabilityPage } from './ObservabilityPage';
import { PersonaFlavorReviewModal } from './persona/PersonaFlavorReviewModal';
import { SidebarNav } from './SidebarNav';
import { SectionErrorBoundary } from './SectionErrorBoundary';
import { TopCommandBar } from './TopCommandBar';
import { WorkflowsPage } from './WorkflowsPage';
import { useIsMobile } from '../lib/responsive';
import { shouldShowMobileSectionHeader } from '../lib/mobileCopy';
import { appSectionFromPathname } from '../lib/appSectionRouting';

// Sections that own their full frame edge-to-edge: the market workstation and the ticker
// have their own chrome, Agents is a resizable stage, and Home lays out its own grid with
// its own padding. Everything else is a document and gets a real gutter — previously
// nothing did, which is why utility cards sat flush against the sidebar on one side and
// the scrollbar on the other.
const FULL_BLEED_SECTIONS = new Set(['home', 'agents', 'market']);

// …but only Market and Agents fill the frame exactly. Home is a grid of panels taller than
// one screen, so it scrolls without taking the shell gutter on top of its own.
const FIXED_HEIGHT_SECTIONS = new Set(['agents', 'market']);

// The command row is redundant wherever the section already carries its own search: the
// market workstation and ticker both have a symbol jump in their market bar, and Agents
// has the session drawer. ⌘K still reaches the palette from all of them.
const COMMAND_BAR_SECTIONS = new Set(['home', 'data-tools', 'observability', 'workflows', 'experiments']);

function AppSectionContent() {
  const currentSection = useAppStore((state) => state.currentSection);

  if (currentSection === 'home') {
    return <HomePage />;
  }

  if (currentSection === 'agents') {
    return <AgentsPage />;
  }

  if (currentSection === 'market') {
    return <MarketMonitor />;
  }

  if (currentSection === 'workflows') {
    return <WorkflowsPage />;
  }

  if (currentSection === 'data-tools') {
    return <DataToolsPage />;
  }

  if (currentSection === 'observability') {
    return <ObservabilityPage />;
  }

  return <ExperimentsPage />;
}

export function AppShell() {
  const themeMode = useAppStore((state) => state.themeMode);
  const currentSection = useAppStore((state) => state.currentSection);
  const isMobile = useIsMobile();
  const showMobileTopBar = isMobile && shouldShowMobileSectionHeader(currentSection);

  useEffect(() => {
    void wsClient.connect();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode;
  }, [themeMode]);

  useEffect(() => {
    const syncSectionFromLocation = () => {
      useAppStore.setState({
        currentSection: appSectionFromPathname(window.location.pathname),
      });
    };
    syncSectionFromLocation();
    window.addEventListener('popstate', syncSectionFromLocation);
    return () => window.removeEventListener('popstate', syncSectionFromLocation);
  }, []);

  return (
    <div className="flex h-screen w-full max-w-full overflow-x-hidden overflow-y-hidden bg-shell-bg text-shell-text">
      <CommandPalette />
      <PersonaFlavorReviewModal />
      <div className="relative flex h-full w-full max-w-full overflow-x-hidden">
        {!isMobile && <SidebarNav />}
        <div
          className={`shell-app-frame flex min-w-0 flex-1 max-w-full flex-col overflow-x-hidden overflow-y-hidden bg-shell-canvas ${
            isMobile ? 'pb-[calc(env(safe-area-inset-bottom)+6rem)]' : ''
          }`}
        >
          {showMobileTopBar && <MobileTopBar />}
          <ConnectionBanner />
          {!isMobile && COMMAND_BAR_SECTIONS.has(currentSection) && (
            <div className="flex shrink-0 items-center gap-2 border-b border-shell-border px-3 py-2">
              <TopCommandBar />
            </div>
          )}
          <div
            className={`min-h-0 flex-1 overflow-x-hidden ${
              FIXED_HEIGHT_SECTIONS.has(currentSection)
                ? 'overflow-y-hidden'
                : `overflow-y-auto ${FULL_BLEED_SECTIONS.has(currentSection) ? '' : 'shell-section-gutter'}`
            } ${isMobile && !showMobileTopBar ? 'pt-[calc(env(safe-area-inset-top)+0.5rem)]' : ''}`}
          >
            <SectionErrorBoundary sectionName={currentSection}>
              <AppSectionContent />
            </SectionErrorBoundary>
          </div>
        </div>
        {isMobile && <MobileBottomNav />}
      </div>
    </div>
  );
}
