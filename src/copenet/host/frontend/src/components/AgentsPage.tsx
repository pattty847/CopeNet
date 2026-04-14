import { ChatWorkspace } from './ChatWorkspace';
import { RightPanel } from './RightPanel';
import { SessionSidebar } from './SessionSidebar';

export function AgentsPage() {
  return (
    <div className="flex h-full min-h-0 gap-5">
      <div className="min-h-0 shrink-0 overflow-hidden rounded-[28px] border border-shell-border bg-shell-operator-frame shadow-shell">
        <SessionSidebar />
      </div>
      <div className="min-h-0 flex-1 overflow-hidden rounded-[28px] border border-shell-border bg-shell-operator-frame shadow-shell">
        <ChatWorkspace />
      </div>
      <div className="min-h-0 shrink-0 overflow-hidden rounded-[28px] border border-shell-border bg-shell-operator-frame shadow-shell">
        <RightPanel />
      </div>
    </div>
  );
}
