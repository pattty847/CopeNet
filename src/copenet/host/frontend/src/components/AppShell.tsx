import { useEffect } from 'react';
import { wsClient } from '../lib/wsClient';
import { useAppStore } from '../store/useAppStore';
import { AgentsPage } from './AgentsPage';
import { CommandPalette } from './CommandPalette';
import { ConnectionBanner } from './ConnectionBanner';
import { DataToolsPage } from './DataToolsPage';
import { ExperimentsPage } from './ExperimentsPage';
import { HomePage } from './HomePage';
import { ObservabilityPage } from './ObservabilityPage';
import { SidebarNav } from './SidebarNav';
import { TopCommandBar } from './TopCommandBar';
import { WorkflowsPage } from './WorkflowsPage';

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

  useEffect(() => {
    void wsClient.connect();
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = themeMode;
  }, [themeMode]);

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-shell-bg text-shell-text">
      <div className="absolute inset-0 shell-backdrop pointer-events-none" />
      <CommandPalette />
      <div className="relative flex h-full w-full gap-3 p-3">
        <SidebarNav />
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden rounded-[24px] border border-shell-border bg-shell-canvas px-4 pb-4 pt-3 shadow-shell-xl">
          <ConnectionBanner />
          <div className="flex items-center gap-3 pb-3">
            <TopCommandBar />
          </div>
          <div className="min-h-0 flex-1 overflow-auto">
            <AppSectionContent />
          </div>
        </div>
      </div>
    </div>
  );
}
