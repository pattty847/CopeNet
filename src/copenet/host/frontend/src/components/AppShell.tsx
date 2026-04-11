import { useEffect } from 'react';
import { wsClient } from '../lib/wsClient';
import { TopStatusBar } from './TopStatusBar';
import { SessionSidebar } from './SessionSidebar';
import { ChatWorkspace } from './ChatWorkspace';
import { RightPanel } from './RightPanel';

export function AppShell() {
  useEffect(() => {
    wsClient.connect();
  }, []);

  return (
    <div className="flex flex-col h-screen w-screen overflow-hidden bg-operator-bg text-operator-text">
      <TopStatusBar />
      <div className="flex flex-1 overflow-hidden">
        <SessionSidebar />
        <ChatWorkspace />
        <RightPanel />
      </div>
    </div>
  );
}
