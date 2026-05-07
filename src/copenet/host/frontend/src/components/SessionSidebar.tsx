import React, { useEffect, MouseEvent } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { ArchiveRestore, Archive, CheckSquare, ChevronLeft, ChevronRight, GitMerge, Plus, Square } from 'lucide-react';

function timeAgo(dateString?: string | null) {
  if (!dateString) return 'Just now';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  if (diffHours < 1) return 'Just now';
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

function compactModelName(model?: string | null) {
  if (!model) return '';
  const normalized = model.trim();
  if (!normalized) return '';
  if (normalized.length <= 18) return normalized;

  const segments = normalized.split('-').filter(Boolean);
  if (segments.length >= 3) {
    const head = segments.slice(0, 2).join('-');
    const tail = segments[segments.length - 1];
    const shortened = `${head}-…-${tail}`;
    if (shortened.length <= 20) return shortened;
  }

  return `${normalized.slice(0, 16)}…`;
}

export function SessionSidebar({ mobile = false }: { mobile?: boolean }) {
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
  const providers = useAppStore((state) => state.providers);
  const sidebarOpen = useAppStore((state) => state.sidebarOpen);
  const setSidebarOpen = useAppStore((state) => state.setSidebarOpen);

  const filteredSessions = sessions.filter((session) => session.archived === showArchived);

  useEffect(() => {
    void wsClient.refreshSessions();
  }, [showArchived]);

  const handleNewSession = () => {
    clearSelectedSessionKeys();
    setSessionSelectMode(false);
    setMergeDraft(null);
    wsClient.beginDraft();
  };

  const handleSessionSelect = (sessionKey: string) => {
    if (sessionSelectMode) {
      toggleSelectedSessionKey(sessionKey);
      return;
    }
    setDraftOpen(false);
    setMergeDraft(null);
    setActiveSessionKey(sessionKey);
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

  if (!sidebarOpen) {
    return (
      <aside className={`${mobile ? 'hidden' : 'w-11'} bg-operator-bg flex flex-col h-full items-center py-3 gap-3`}>
        <button
          onClick={() => setSidebarOpen(true)}
          className="flex h-8 w-8 items-center justify-center rounded-xl text-operator-muted hover:text-operator-accent hover:bg-operator-panel transition-all duration-150"
          title="Expand session list"
        >
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={handleNewSession}
          className="flex h-8 w-8 items-center justify-center rounded-xl bg-operator-accent/10 text-operator-accent hover:bg-operator-accent/20 transition-all duration-150"
          title="New Chat"
        >
          <Plus className="w-3.5 h-3.5" />
        </button>
        <div className="mt-auto flex flex-col gap-2 items-center">
          <div className="text-[9px] font-semibold text-operator-muted -rotate-90 whitespace-nowrap">
            {filteredSessions.length} sessions
          </div>
        </div>
      </aside>
    );
  }

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
            <button
              onClick={() => setSidebarOpen(false)}
              className="p-1.5 text-operator-muted hover:text-operator-accent transition-colors duration-150 rounded-md hover:bg-operator-panel shrink-0"
              title="Collapse sidebar"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
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

        {filteredSessions.map((session) => {
          const isActive = activeSessionKey === session.key;
          const isSelected = selectedSessionKeys.includes(session.key);
          const providerName = providers.find((provider) => provider.id === session.provider)?.displayName || session.provider;
          const modelLabel = compactModelName(session.model);

          return (
            <div
              key={session.key}
              onClick={() => handleSessionSelect(session.key)}
              className={`w-full flex flex-col px-2 py-1.5 text-[12px] transition-all duration-150 cursor-pointer group relative ${
                sessionSelectMode
                  ? isSelected
                    ? 'bg-operator-panel/30 border-y border-operator-accent/16'
                    : 'hover:bg-operator-panel/16 border-y border-transparent'
                  : isActive
                  ? 'bg-operator-panel/36 border-y border-operator-accent/18'
                  : 'hover:bg-operator-panel/20 border-y border-transparent'
              }`}
            >
              {!sessionSelectMode && isActive && <div className="absolute left-0 top-1.5 bottom-1.5 w-[2px] rounded-full bg-operator-accent" />}
              <div className="flex justify-between items-start gap-2">
                <div className="flex min-w-0 items-start gap-2 pr-5">
                  {sessionSelectMode && !showArchived ? (
                    <span className={`mt-0.5 flex h-4 w-4 items-center justify-center rounded-sm border ${isSelected ? 'border-operator-accent bg-operator-accent/12 text-operator-accent' : 'border-operator-border text-transparent'}`}>
                      <CheckSquare className="w-3 h-3" />
                    </span>
                  ) : null}
                  <span className={`font-semibold truncate text-[12px] ${isActive || isSelected ? 'text-operator-text' : 'text-operator-muted group-hover:text-operator-text'} transition-colors duration-150`}>
                    {session.title || session.key || 'New Chat'}
                  </span>
                </div>
                {!sessionSelectMode && (
                  <button
                    onClick={(e) => handleArchiveToggle(e, session.key, session.archived)}
                    className="absolute top-1.5 right-1.5 opacity-0 group-hover:opacity-100 text-operator-muted hover:text-operator-accent transition-all duration-150"
                    title={session.archived ? 'Restore Session' : 'Archive Session'}
                  >
                    {session.archived ? <ArchiveRestore className="w-3 h-3" /> : <Archive className="w-3 h-3" />}
                  </button>
                )}
              </div>

              <div className="mt-0.5 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 text-[10px] text-operator-muted/80">
                <div className="flex min-w-0 items-center gap-1.5 overflow-hidden">
                  <span className="min-w-0 truncate" title={providerName}>{providerName}</span>
                  {modelLabel && (
                    <>
                      <span className="text-operator-muted/30">·</span>
                      <span className="min-w-0 truncate font-medium text-operator-text/88" title={session.model || undefined}>{modelLabel}</span>
                    </>
                  )}
                </div>
                <span className="shrink-0 text-[10px] text-operator-muted/45 tabular-nums">{timeAgo(session.createdAt)}</span>
              </div>
            </div>
          );
        })}
        {filteredSessions.length === 0 && (
          <div className="text-center text-operator-muted text-[12px] py-8 px-3 leading-relaxed">
            {showArchived ? 'No archived sessions yet.' : 'No saved sessions yet. Start a draft and send your first message.'}
          </div>
        )}
      </div>
    </aside>
  );
}
