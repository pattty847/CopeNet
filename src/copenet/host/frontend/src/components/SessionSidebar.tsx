import React, { useEffect, MouseEvent } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { ArchiveRestore, Archive, ChevronLeft, ChevronRight } from 'lucide-react';

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

export function SessionSidebar() {
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
      <aside className="w-10 border-r border-operator-border bg-operator-bg flex flex-col h-full items-center pt-2">
        <button
          onClick={() => setSidebarOpen(true)}
          className="p-2 text-operator-muted hover:text-operator-accent transition-colors"
          title="Expand sidebar"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </aside>
    );
  }

  return (
    <aside className="w-72 border-r border-operator-border bg-operator-bg flex flex-col h-full">
      <div className="p-4 border-b border-operator-border flex items-center gap-2">
        <button
          onClick={handleNewSession}
          className="flex-1 py-2 bg-operator-accent text-operator-bg font-mono font-bold text-sm hover:opacity-90 transition-opacity rounded-sm"
        >
          New Chat
        </button>
        <button
          onClick={() => setSidebarOpen(false)}
          className="p-2 text-operator-muted hover:text-operator-accent transition-colors"
          title="Collapse sidebar"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      <div className="flex border-b border-operator-border text-xs font-mono">
        <button
          className={`flex-1 py-2 text-center transition-colors ${!showArchived ? 'text-operator-accent border-b-2 border-operator-accent bg-operator-panel' : 'text-operator-muted hover:text-operator-text'}`}
          onClick={() => setShowArchived(false)}
        >
          ACTIVE
        </button>
        <button
          className={`flex-1 py-2 text-center transition-colors ${showArchived ? 'text-operator-accent border-b-2 border-operator-accent bg-operator-panel' : 'text-operator-muted hover:text-operator-text'}`}
          onClick={() => setShowArchived(true)}
        >
          ARCHIVED
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {draftOpen && !showArchived && (
          <div className="w-full flex flex-col p-3.5 text-sm font-mono rounded-md border border-operator-accent/40 bg-operator-accent/8 shadow-sm">
            <div className="flex items-center justify-between gap-3 mb-2">
              <span className="font-bold text-operator-text truncate">New Draft Session</span>
              <span className="text-[10px] uppercase tracking-wider text-operator-accent">Draft</span>
            </div>
            <div className="text-xs text-operator-muted leading-relaxed">
              Configure the runtime in the right panel, then send your first message to create and lock the session.
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
              className={`w-full flex flex-col p-3 text-sm font-mono rounded-md transition-colors cursor-pointer group relative ${
                isActive
                  ? 'bg-operator-panel border border-operator-accent/30 shadow-sm'
                  : 'hover:bg-operator-panel/50 border border-transparent'
              }`}
            >
              {isActive && <div className="absolute left-0 top-3 bottom-3 w-0.5 rounded-full bg-operator-accent" />}
              <div className="flex justify-between items-start mb-1">
                <span className={`font-bold truncate pr-6 ${isActive ? 'text-operator-text' : 'text-operator-muted group-hover:text-operator-text'}`}>
                  {session.title || session.key || 'New Chat'}
                </span>
                <button
                  onClick={(e) => handleArchiveToggle(e, session.key, session.archived)}
                  className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 text-operator-muted hover:text-operator-accent transition-opacity"
                  title={session.archived ? 'Restore Session' : 'Archive Session'}
                >
                  {session.archived ? <ArchiveRestore className="w-3.5 h-3.5" /> : <Archive className="w-3.5 h-3.5" />}
                </button>
              </div>

              <div className="flex flex-wrap gap-1.5 mb-2">
                {session.provider && (
                  <span className="px-1.5 py-0.5 bg-operator-border/50 text-operator-muted rounded-full text-[10px] border border-operator-border truncate max-w-[80px]">
                    {providerName}
                  </span>
                )}
                {session.model && (
                  <span className="px-1.5 py-0.5 bg-operator-border/50 text-operator-muted rounded-full text-[10px] border border-operator-border truncate max-w-[120px]">
                    {session.model}
                  </span>
                )}
                {session.systemPromptId && (
                  <span className="px-1.5 py-0.5 bg-operator-border/50 text-operator-muted rounded-full text-[10px] border border-operator-border truncate max-w-[80px]">
                    {session.systemPromptId}
                  </span>
                )}
              </div>

              <div className="text-[10px] text-operator-muted/50 mt-auto">{timeAgo(session.createdAt)}</div>
            </div>
          );
        })}
        {filteredSessions.length === 0 && (
          <div className="text-center text-operator-muted text-xs font-mono py-8 px-4 leading-relaxed">
            {showArchived ? 'No archived sessions yet.' : 'No saved sessions yet. Start a draft and send your first message.'}
          </div>
        )}
      </div>
    </aside>
  );
}
