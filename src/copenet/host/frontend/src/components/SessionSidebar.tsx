import React, { useEffect, useMemo, MouseEvent } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { CheckSquare, GitMerge, Plus, Square } from 'lucide-react';
import { buildSessionRow, groupRowsByArea, NO_CHANGE_AREA } from '../runtime/sessionStanding';
import { SessionStandingRow } from './session/SessionStandingRow';

export function SessionSidebar({ mobile = false, onNavigate }: { mobile?: boolean; onNavigate?: () => void }) {
  const sessions = useAppStore((state) => state.sessions);
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const setActiveSessionKey = useAppStore((state) => state.setActiveSessionKey);
  const draftOpen = useAppStore((state) => state.draftOpen);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);
  const showArchived = useAppStore((state) => state.showArchived);
  const setShowArchived = useAppStore((state) => state.setShowArchived);
  const sessionSelectMode = useAppStore((state) => state.sessionSelectMode);
  const setSessionSelectMode = useAppStore((state) => state.setSessionSelectMode);
  const selectedSessionKeys = useAppStore((state) => state.selectedSessionKeys);
  const toggleSelectedSessionKey = useAppStore((state) => state.toggleSelectedSessionKey);
  const clearSelectedSessionKeys = useAppStore((state) => state.clearSelectedSessionKeys);
  const setMergeDraft = useAppStore((state) => state.setMergeDraft);
  const sessionStanding = useAppStore((state) => state.sessionStanding);
  const activeRunsBySession = useAppStore((state) => state.activeRunsBySession);
  const liveToolCallsByRun = useAppStore((state) => state.liveToolCallsByRun);
  const filteredSessions = sessions.filter((session) => session.archived === showArchived);

  useEffect(() => {
    void wsClient.refreshSessions();
  }, [showArchived]);

  // One derivation for every row (runtime/sessionStanding.ts). The standing facts
  // arrive with the session list in a single call; this used to be an N+1
  // sessions.state fetch that ran again on every list change.
  const groups = useMemo(
    () =>
      groupRowsByArea(
        filteredSessions.map((session) => {
          const runId = activeRunsBySession[session.key];
          return buildSessionRow(
            session,
            sessionStanding[session.key],
            runId ? liveToolCallsByRun[runId] || [] : [],
          );
        }),
      ),
    [filteredSessions, sessionStanding, activeRunsBySession, liveToolCallsByRun],
  );
  const sessionsByKey = useMemo(
    () => new Map(filteredSessions.map((session) => [session.key, session])),
    [filteredSessions],
  );

  const handleNewSession = () => {
    clearSelectedSessionKeys();
    setSessionSelectMode(false);
    setMergeDraft(null);
    // The Chat|Fleet toggle is the context: New in Fleet mode means a new
    // Fleet room (the create screen handles archiving the current one).
    if (useAppStore.getState().agentsWorkspaceMode === 'fleet') {
      useAppStore.getState().setFleetCreateOpen(true);
    } else {
      wsClient.beginDraft();
    }
    onNavigate?.();   // close the mobile sessions sheet after starting a draft
  };

  const handleSessionSelect = (sessionKey: string) => {
    if (sessionSelectMode) {
      toggleSelectedSessionKey(sessionKey);
      return;
    }
    setDraftOpen(false);
    setMergeDraft(null);
    useAppStore.getState().setAgentsWorkspaceMode('chat');
    setActiveSessionKey(sessionKey);
    onNavigate?.();   // close the mobile sessions sheet and go straight to the session
  };

  const handleMergeIntoWorkspace = () => {
    if (selectedSessionKeys.length < 2) return;
    setMergeDraft({ sourceSessionKeys: selectedSessionKeys });
    setDraftOpen(true);
    setActiveSessionKey(null);
    setSessionSelectMode(false);
    clearSelectedSessionKeys();
  };

  const handleArchiveToggle = (e: MouseEvent, sessionKey: string, archived: boolean) => {
    e.stopPropagation();
    void wsClient.archiveSession(sessionKey, !archived);
    if (!archived && activeSessionKey === sessionKey) {
      setActiveSessionKey(null);
    }
  };

  return (
    <aside className={`${mobile ? 'w-full border-r-0' : 'w-full border-r'} border-operator-border bg-operator-bg flex h-full flex-col`}>
      {/* Header */}
      <div className="border-b border-operator-border px-2.5 py-2">
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-operator-accent">Session Fleet</span>
            <span className="text-[10px] text-operator-muted/60 tabular-nums">
              {filteredSessions.length}
            </span>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {!showArchived && (
              <button
                onClick={() => {
                  const next = !sessionSelectMode;
                  setSessionSelectMode(next);
                  if (!next) clearSelectedSessionKeys();
                }}
                className={`flex h-7 items-center justify-center rounded-md border px-2 text-[10px] font-semibold uppercase tracking-[0.12em] transition-colors ${
                  sessionSelectMode
                    ? 'border-operator-accent/30 bg-operator-accent/10 text-operator-accent'
                    : 'border-operator-border text-operator-muted hover:text-operator-accent'
                }`}
                title={sessionSelectMode ? 'Exit select mode' : 'Select sessions'}
              >
                {sessionSelectMode ? <CheckSquare className="w-3 h-3" /> : <Square className="w-3 h-3" />}
              </button>
            )}
          </div>
        </div>

        {sessionSelectMode && !showArchived ? (
          <div className="flex items-center gap-1.5">
            <button
              onClick={handleMergeIntoWorkspace}
              disabled={selectedSessionKeys.length < 2}
              className="glow-accent flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-lg bg-operator-accent py-1.5 text-[11px] font-semibold text-operator-bg disabled:cursor-not-allowed disabled:opacity-40"
            >
              <GitMerge className="w-3.5 h-3.5" />
              Merge Into Workspace
            </button>
            <span className="text-[10px] text-operator-muted/70 tabular-nums">{selectedSessionKeys.length} selected</span>
          </div>
        ) : (
          <button
            onClick={handleNewSession}
            className="glow-accent flex w-full items-center justify-center gap-1.5 rounded-lg bg-operator-accent py-1.5 text-[11px] font-semibold text-operator-bg"
          >
            <Plus className="w-3.5 h-3.5" />
            New Chat
          </button>
        )}
      </div>

      {/* Tabs */}
      <div className="flex border-b border-operator-border text-[10px] font-semibold tracking-wider">
        <button
          className={`flex-1 py-1 text-center transition-colors duration-150 ${!showArchived ? 'text-operator-accent border-b-2 border-operator-accent bg-operator-panel/40' : 'text-operator-muted hover:text-operator-text'}`}
          onClick={() => setShowArchived(false)}
        >
          ACTIVE
        </button>
        <button
          className={`flex-1 py-1 text-center transition-colors duration-150 ${showArchived ? 'text-operator-accent border-b-2 border-operator-accent bg-operator-panel/40' : 'text-operator-muted hover:text-operator-text'}`}
          onClick={() => setShowArchived(true)}
        >
          ARCHIVED
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 space-y-0.5 overflow-y-auto p-1">
        {draftOpen && !showArchived && (
          <div className="w-full flex flex-col border border-operator-accent/20 border-x-0 px-2 py-1.5 text-[12px]">
            <div className="flex items-center justify-between gap-2">
              <span className="font-semibold text-operator-text truncate">New Draft Session</span>
              <span className="text-[9px] uppercase tracking-wider text-operator-accent font-semibold">Draft</span>
            </div>
            <div className="mt-0.5 text-[10px] text-operator-muted truncate">
              Configure runtime, then send.
            </div>
          </div>
        )}

        {groups.map((group) => (
          <div key={group.area}>
            {/* Group by the area the work lives in — you remember by place, not by clock. */}
            <div className="flex items-center gap-[7px] px-3 pb-1 pt-2">
              <span
                className={`font-mono text-[9.5px] font-semibold uppercase tracking-[0.1em] ${
                  group.area === NO_CHANGE_AREA ? 'text-operator-muted/75' : 'text-operator-accent'
                }`}
              >
                {group.area}
              </span>
              <span className="h-px flex-grow bg-operator-border" />
              <span className="text-[9.5px] tabular-nums text-operator-muted/50">{group.rows.length}</span>
            </div>
            {group.rows.map((row) => {
              const session = sessionsByKey.get(row.sessionKey);
              if (!session) return null;
              return (
                <SessionStandingRow
                  key={row.sessionKey}
                  row={row}
                  age={session.updatedAt || session.createdAt}
                  active={activeSessionKey === row.sessionKey}
                  selected={selectedSessionKeys.includes(row.sessionKey)}
                  selectMode={sessionSelectMode}
                  archived={session.archived}
                  onSelect={() => handleSessionSelect(row.sessionKey)}
                  onArchiveToggle={(event) => handleArchiveToggle(event, row.sessionKey, session.archived)}
                />
              );
            })}
          </div>
        ))}

        {filteredSessions.length === 0 && (
          <div className="text-center text-operator-muted text-[12px] py-8 px-3 leading-relaxed">
            {showArchived ? 'No archived sessions yet.' : 'No saved sessions yet. Start a draft and send your first message.'}
          </div>
        )}
      </div>
    </aside>
  );
}
