import { Activity } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { ConnectionBanner } from './ConnectionBanner';

export function TopStatusBar() {
  const activeRunId = useAppStore((state) => state.activeRunId);
  const wsStatus = useAppStore((state) => state.wsStatus);

  const systemLabel =
    wsStatus === 'connected' ? 'Online' : wsStatus === 'auth_failed' ? 'Auth Failed' : 'Offline';

  return (
    <div className="flex flex-col w-full z-10">
      <ConnectionBanner />
      <header className="h-12 border-b border-operator-border bg-operator-panel flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <div className="font-mono font-bold tracking-tight text-operator-text flex items-center gap-2">
            <div className="w-2 h-2 bg-operator-accent rounded-sm" />
            COPENET
          </div>
        </div>

        <div className="flex items-center gap-4 text-xs font-mono text-operator-muted">
          {activeRunId && (
            <div className="flex items-center gap-2 text-operator-accent">
              <Activity className="w-3 h-3 animate-pulse" />
              <span>RUN: {activeRunId.slice(0, 8)}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="uppercase">System: {systemLabel}</span>
          </div>
        </div>
      </header>
    </div>
  );
}
