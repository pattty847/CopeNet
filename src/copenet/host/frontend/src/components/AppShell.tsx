import { useEffect } from 'react';
import { wsClient } from '../lib/wsClient';
import { useAppStore } from '../store/useAppStore';
import { AgentsPage } from './AgentsPage';
import { CommandPalette } from './CommandPalette';
import { ConnectionBanner } from './ConnectionBanner';
import { DataToolsPage } from './DataToolsPage';
import { ExperimentsPage } from './ExperimentsPage';
import { HomePage } from './HomePage';
import { MobileBottomNav, MobileTopBar } from './mobile/MobileNav';
import { ObservabilityPage } from './ObservabilityPage';
import { SidebarNav } from './SidebarNav';
import { TopCommandBar } from './TopCommandBar';
import { WorkflowsPage } from './WorkflowsPage';
import { useIsMobile } from '../lib/responsive';
import { shouldShowMobileSectionHeader } from '../lib/mobileCopy';

function AppSectionContent() {
  const currentSection = useAppStore((state) => state.currentSection);

  if (currentSection === 'home') {
    return <HomePage />;
  }

  if (currentSection === 'agents') {
    return <AgentsPage />;
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

  return (
    <div className="flex h-screen w-full max-w-full overflow-x-hidden overflow-y-hidden bg-shell-bg text-shell-text">
      <div className="absolute inset-0 shell-backdrop pointer-events-none" />
      <CommandPalette />
      <div className={`relative flex h-full w-full max-w-full overflow-x-hidden ${isMobile ? 'p-0' : 'gap-3 p-3'}`}>
        {!isMobile && <SidebarNav />}
        <div
          className={`shell-app-frame flex min-w-0 flex-1 max-w-full flex-col overflow-x-hidden overflow-y-hidden border border-shell-border bg-shell-canvas shadow-shell-xl ${
            isMobile ? 'rounded-none border-x-0 border-t-0 pb-[calc(env(safe-area-inset-bottom)+6rem)]' : 'rounded-[24px] px-4 pb-4 pt-3'
          }`}
        >
          {showMobileTopBar && <MobileTopBar />}
          <ConnectionBanner />
          {!isMobile && currentSection !== 'agents' && (
            <div className="flex items-center gap-3 pb-3">
              <TopCommandBar />
            </div>
          )}
          <div className={`min-h-0 flex-1 overflow-x-hidden overflow-y-auto ${isMobile && !showMobileTopBar ? 'pt-[calc(env(safe-area-inset-top)+0.5rem)]' : ''}`}>
            <AppSectionContent />
          </div>
        </div>
        {isMobile && <MobileBottomNav />}
      </div>
    </div>
  );
}
