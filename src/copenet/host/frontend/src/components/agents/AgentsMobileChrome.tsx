// The Agents chrome, as two pieces a workspace header can absorb.
//
// On a phone this section used to stack three separate 40–58px bars before a single message
// was visible: the panel buttons, the Chat/Fleet switch, and the session title with its
// actions menu. Each one is a different owner (AgentsPage, AgentsWorkspaceSurface,
// ChatWorkspace/FleetWorkspace), which is exactly why nobody noticed them adding up to
// 155px of a 932px screen. The controls are small; it is the ROWS that are expensive.
//
// So the two store-driven controls live here and are rendered INSIDE the workspace's own
// title row, leaving one bar. Both read and write the store directly — they take no props
// precisely so a header can drop them in without threading state through itself.

import { MessagesSquare, PanelLeft, SlidersHorizontal, UsersRound } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';

/** Sessions and Inspector, as icons. The labels were the first thing to go: the sheet each
 *  one opens is titled, and on a phone the two words cost more than they explain. */
export function MobilePanelButtons() {
  const setMobileSessionsOpen = useAppStore((state) => state.setMobileSessionsOpen);
  const setMobileInspectorOpen = useAppStore((state) => state.setMobileInspectorOpen);

  return (
    <div className="flex shrink-0 items-center gap-1">
      <button
        type="button"
        onClick={() => setMobileSessionsOpen(true)}
        aria-label="Open sessions"
        title="Sessions"
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-operator-border bg-operator-panel/60 text-shell-accent"
      >
        <PanelLeft className="h-4 w-4" />
      </button>
      <button
        type="button"
        onClick={() => setMobileInspectorOpen(true)}
        aria-label="Open inspector"
        title="Inspector"
        className="flex h-8 w-8 items-center justify-center rounded-lg border border-operator-border bg-operator-panel/60 text-shell-accent"
      >
        <SlidersHorizontal className="h-4 w-4" />
      </button>
    </div>
  );
}

/** The Chat/Fleet switch. `compact` drops the words for the phone row; the pulse dot stays
 *  either way, because an unattended Fleet lane working is the one thing worth the pixels. */
export function WorkspaceModeSwitch({ compact = false }: { compact?: boolean }) {
  const mode = useAppStore((state) => state.agentsWorkspaceMode);
  const setMode = useAppStore((state) => state.setAgentsWorkspaceMode);
  const rooms = useAppStore((state) => state.fleetRooms);
  const pendingByRoom = useAppStore((state) => state.fleetPendingCountsByRoom);
  const activeRoom = rooms.find((room) => room.status === 'active');
  const fleetWorking = activeRoom
    ? Object.values(pendingByRoom[activeRoom.roomId] || {}).some((count) => count > 0)
    : false;

  const pad = compact ? 'px-2' : 'px-3';
  const base = `relative flex items-center gap-1.5 rounded-md ${pad} py-1 text-[10px] font-semibold transition`;
  const on = 'bg-operator-panel text-operator-text shadow-sm';
  const off = 'text-operator-muted hover:text-operator-text';

  return (
    <div className="flex shrink-0 rounded-lg border border-operator-border bg-operator-bg/55 p-0.5">
      <button
        type="button"
        onClick={() => setMode('chat')}
        aria-label="Chat"
        title="Chat"
        className={`${base} ${mode === 'chat' ? on : off}`}
      >
        <MessagesSquare className="h-3 w-3" />
        {!compact && 'Chat'}
      </button>
      <button
        type="button"
        onClick={() => setMode('fleet')}
        aria-label="Fleet"
        title="Fleet"
        className={`${base} ${mode === 'fleet' ? on : off}`}
      >
        <UsersRound className="h-3 w-3" />
        {!compact && 'Fleet'}
        {fleetWorking && <span className="absolute -right-1 -top-1 h-2 w-2 animate-pulse rounded-full bg-operator-accent" />}
      </button>
    </div>
  );
}
