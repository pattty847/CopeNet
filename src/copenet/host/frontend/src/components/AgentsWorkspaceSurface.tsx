import { MessagesSquare, UsersRound } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { ChatWorkspace } from './ChatWorkspace';
import { FleetWorkspace } from './fleet/FleetWorkspace';

export function AgentsWorkspaceSurface() {
  const mode = useAppStore((state) => state.agentsWorkspaceMode);
  const setMode = useAppStore((state) => state.setAgentsWorkspaceMode);
  const rooms = useAppStore((state) => state.fleetRooms);
  const pendingByRoom = useAppStore((state) => state.fleetPendingCountsByRoom);
  const activeRoom = rooms.find((room) => room.status === 'active');
  const fleetWorking = activeRoom
    ? Object.values(pendingByRoom[activeRoom.roomId] || {}).some((count) => count > 0)
    : false;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex h-10 shrink-0 items-center justify-between border-b border-operator-border bg-operator-panel/45 px-3">
        <div className="flex rounded-lg border border-operator-border bg-operator-bg/55 p-0.5">
          <button type="button" onClick={() => setMode('chat')} className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-[10px] font-semibold transition ${mode === 'chat' ? 'bg-operator-panel text-operator-text shadow-sm' : 'text-operator-muted hover:text-operator-text'}`}>
            <MessagesSquare className="h-3 w-3" /> Chat
          </button>
          <button type="button" onClick={() => setMode('fleet')} className={`relative flex items-center gap-1.5 rounded-md px-3 py-1 text-[10px] font-semibold transition ${mode === 'fleet' ? 'bg-operator-panel text-operator-text shadow-sm' : 'text-operator-muted hover:text-operator-text'}`}>
            <UsersRound className="h-3 w-3" /> Fleet
            {fleetWorking && <span className="absolute -right-1 -top-1 h-2 w-2 animate-pulse rounded-full bg-operator-accent" />}
          </button>
        </div>
        {activeRoom && mode !== 'fleet' && (
          <button type="button" onClick={() => setMode('fleet')} className="max-w-[45%] truncate text-[10px] text-operator-muted transition hover:text-operator-accent">
            {fleetWorking ? 'Fleet is working · ' : 'Fleet ready · '}{activeRoom.title}
          </button>
        )}
      </div>
      <div className="min-h-0 flex-1">{mode === 'fleet' ? <FleetWorkspace /> : <ChatWorkspace />}</div>
    </div>
  );
}
