import React, { useEffect, MouseEvent } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { ArchiveRestore, Archive, Bug, ChevronLeft, ChevronRight, Download, Plus } from 'lucide-react';

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

export function SessionSidebar({ mobile = false }: { mobile?: boolean }) {
  const sessions = useAppStore((state) => state.sessions);
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const setActiveSessionKey = useAppStore((state) => state.setActiveSessionKey);
  const draftOpen = useAppStore((state) => state.draftOpen);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);
  const showArchived = useAppStore((state) => state.showArchived);
  const setShowArchived = useAppStore((state) => state.setShowArchived);
  const providers = useAppStore((state) => state.providers);
  const sidebarOpen = useAppStore((state) => state.sidebarOpen);
  const setSidebarOpen = useAppStore((state) => state.setSidebarOpen);

  const filteredSessions = sessions.filter((session) => session.archived === showArchived);
  const activeSession = sessions.find((session) => session.key === activeSessionKey) || null;

  useEffect(() => {
    void wsClient.refreshSessions();
  }, [showArchived]);

  const handleNewSession = () => {
    wsClient.beginDraft();
  };

  const handleSessionSelect = (sessionKey: string) => {
    setDraftOpen(false);
    setActiveSessionKey(sessionKey);
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
    <aside className={`${mobile ? 'w-full border-r-0' : 'w-64 border-r'} border-operator-border bg-operator-bg flex h-full flex-col`}>
      {/* Header */}
      <div className="px-3 py-2.5 border-b border-operator-border flex items-center gap-1.5">
        <button
          onClick={handleNewSession}
          className="glow-accent flex-1 flex items-center justify-center gap-1.5 py-1.5 bg-operator-accent text-operator-bg font-sans font-semibold text-[13px] rounded-lg"
        >
          <Plus className="w-3.5 h-3.5" />
          New Chat
        </button>
        <button
          onClick={() => setSidebarOpen(false)}
          className="p-1.5 text-operator-muted hover:text-operator-accent transition-colors duration-150 rounded-lg hover:bg-operator-panel"
          title="Collapse sidebar"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-operator-border text-[11px] font-semibold tracking-wide">
        <button
          className={`flex-1 py-2 text-center transition-colors duration-150 ${!showArchived ? 'text-operator-accent border-b-2 border-operator-accent bg-operator-panel/50' : 'text-operator-muted hover:text-operator-text'}`}
          onClick={() => setShowArchived(false)}
        >
          ACTIVE
        </button>
        <button
          className={`flex-1 py-2 text-center transition-colors duration-150 ${showArchived ? 'text-operator-accent border-b-2 border-operator-accent bg-operator-panel/50' : 'text-operator-muted hover:text-operator-text'}`}
          onClick={() => setShowArchived(true)}
        >
          ARCHIVED
        </button>
      </div>

      {/* Session list */}
      <div className="flex-1 overflow-y-auto p-1.5 space-y-1">
        {activeSession && (
          <div className="mx-1 rounded-xl border border-operator-accent/15 bg-operator-accent/6 px-3 py-2.5">
            <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-operator-accent">
              <Bug className="h-3.5 w-3.5" />
              Debug Tools
            </div>
            <div className="mt-1.5 text-[11px] leading-relaxed text-operator-muted">
              Use the session header to run <span className="text-operator-text">Debug Copy</span> or <span className="text-operator-text">Export</span> for this {activeSession.archived ? 'archived' : 'active'} conversation.
            </div>
            <div className="mt-2 flex items-center gap-1.5 text-[10px] text-operator-muted/80">
              <Download className="h-3 w-3" />
              Metadata, transcript, and tool traces
            </div>
          </div>
        )}

        {draftOpen && !showArchived && (
          <div className="w-full flex flex-col p-2.5 text-[13px] rounded-xl border border-operator-accent/30 bg-operator-accent/8">
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="font-semibold text-operator-text truncate">New Draft Session</span>
              <span className="text-[9px] uppercase tracking-wider text-operator-accent font-semibold">Draft</span>
            </div>
            <div className="text-[11px] text-operator-muted leading-relaxed">
              Configure runtime in the right panel, then send to lock.
            </div>
          </div>
        )}

        {filteredSessions.map((session) => {
          const isActive = activeSessionKey === session.key;
          const providerName = providers.find((provider) => provider.id === session.provider)?.displayName || session.provider;

          return (
            <div
              key={session.key}
              onClick={() => handleSessionSelect(session.key)}
              className={`w-full flex flex-col p-2.5 text-[13px] rounded-xl transition-all duration-150 cursor-pointer group relative ${
                isActive
                  ? 'bg-operator-panel border border-operator-accent/20 shadow-sm'
                  : 'hover:bg-operator-panel/50 border border-transparent'
              }`}
            >
              {isActive && <div className="absolute left-0 top-2.5 bottom-2.5 w-[2.5px] rounded-full bg-operator-accent" />}
              <div className="flex justify-between items-start mb-0.5">
                <span className={`font-semibold truncate pr-5 text-[13px] ${isActive ? 'text-operator-text' : 'text-operator-muted group-hover:text-operator-text'} transition-colors duration-150`}>
                  {session.title || session.key || 'New Chat'}
                </span>
                <button
                  onClick={(e) => handleArchiveToggle(e, session.key, session.archived)}
                  className="absolute top-2.5 right-2.5 opacity-0 group-hover:opacity-100 text-operator-muted hover:text-operator-accent transition-all duration-150"
                  title={session.archived ? 'Restore Session' : 'Archive Session'}
                >
                  {session.archived ? <ArchiveRestore className="w-3 h-3" /> : <Archive className="w-3 h-3" />}
                </button>
              </div>

              <div className="flex flex-wrap gap-1 mb-1.5">
                {session.provider && (
                  <span className="px-1.5 py-0.5 bg-operator-border/40 text-operator-muted rounded-md text-[10px] border border-operator-border/60 truncate max-w-[72px]">
                    {providerName}
                  </span>
                )}
                {session.model && (
                  <span className="px-1.5 py-0.5 bg-operator-border/40 text-operator-muted rounded-md text-[10px] border border-operator-border/60 truncate max-w-[110px]">
                    {session.model}
                  </span>
                )}
                {session.systemPromptId && (
                  <span className="px-1.5 py-0.5 bg-operator-border/40 text-operator-muted rounded-md text-[10px] border border-operator-border/60 truncate max-w-[72px]">
                    {session.systemPromptId}
                  </span>
                )}
              </div>

              <div className="text-[10px] text-operator-muted/50 mt-auto">{timeAgo(session.createdAt)}</div>
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
