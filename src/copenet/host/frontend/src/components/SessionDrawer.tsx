import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  ArchiveRestore,
  CheckSquare,
  GitMerge,
  Pin,
  Plus,
  Search,
  Square,
  Star,
  X,
} from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { organizeSessionDrawerSections } from '../lib/sessionDrawer';
import { describeSessionReturnCue } from '../lib/personalHistory';
import type { Session } from '../types/backend';

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
  return `${normalized.slice(0, 16)}…`;
}

function SessionRow({
  session,
  active,
  selected,
  pinned,
  selecting,
  onOpen,
  onToggleSelect,
  onTogglePin,
  onToggleArchive,
}: {
  session: Session;
  active: boolean;
  selected: boolean;
  pinned: boolean;
  selecting: boolean;
  onOpen: () => void;
  onToggleSelect: () => void;
  onTogglePin: () => void;
  onToggleArchive: () => void;
}) {
  const providers = useAppStore((state) => state.providers);
  const sessionStates = useAppStore((state) => state.sessionStates);
  const providerName = providers.find((provider) => provider.id === session.provider)?.displayName || session.provider;
  const modelLabel = compactModelName(session.model);
  const sessionState = sessionStates[session.key];
  const returnCue = describeSessionReturnCue({
    providerLabel: providerName,
    modelLabel,
    taskSummary: sessionState?.task_summary || null,
    starterIntent: sessionState?.starter_intent || null,
    topicalTags: sessionState?.topical_tags || [],
  });

  return (
    <div
      onClick={selecting ? onToggleSelect : onOpen}
      className={`group relative rounded-2xl border px-3 py-2.5 transition-all duration-150 cursor-pointer ${
        active
          ? 'border-shell-accent/30 bg-shell-accent-soft'
          : selected
            ? 'border-shell-accent/20 bg-shell-panel-strong/70'
            : 'border-shell-border bg-shell-panel hover:border-shell-border-strong hover:bg-shell-panel-strong'
      }`}
    >
      <div className="flex items-start gap-2">
        {selecting && (
          <span className={`mt-0.5 flex h-4 w-4 items-center justify-center rounded-sm border ${selected ? 'border-shell-accent bg-shell-accent-soft text-shell-accent' : 'border-shell-border text-transparent'}`}>
            <CheckSquare className="h-3 w-3" />
          </span>
        )}
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <div className="truncate text-[13px] font-semibold text-shell-text">{session.title || session.key || 'New Chat'}</div>
              <div className="mt-1 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 text-[10px] text-shell-muted/85">
                <div className="min-w-0 truncate" title={returnCue.primary}>{returnCue.primary}</div>
                <span className="text-shell-muted/50 tabular-nums">{timeAgo(session.updatedAt || session.createdAt)}</span>
              </div>
            </div>
            <div className="flex items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100">
              {!session.archived && !selecting && (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onTogglePin();
                  }}
                  className={`rounded-lg p-1.5 transition-colors ${pinned ? 'text-shell-accent' : 'text-shell-muted hover:text-shell-accent'}`}
                  title={pinned ? 'Unpin session' : 'Pin session'}
                >
                  <Star className={`h-3.5 w-3.5 ${pinned ? 'fill-current' : ''}`} />
                </button>
              )}
              {!selecting && (
                <button
                  type="button"
                  onClick={(event) => {
                    event.stopPropagation();
                    onToggleArchive();
                  }}
                  className="rounded-lg p-1.5 text-shell-muted transition-colors hover:text-shell-accent"
                  title={session.archived ? 'Restore session' : 'Archive session'}
                >
                  {session.archived ? <ArchiveRestore className="h-3.5 w-3.5" /> : <Archive className="h-3.5 w-3.5" />}
                </button>
              )}
            </div>
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[10px] text-shell-muted/75">
            <span>{providerName}</span>
            {modelLabel && <span>· {modelLabel}</span>}
            {pinned && (
              <span className="inline-flex items-center gap-1 text-shell-accent">
                <Pin className="h-2.5 w-2.5" /> Pinned
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function SessionSection({
  title,
  sessions,
  activeSessionKey,
  selectedSessionKeys,
  pinnedSessionKeys,
  selecting,
  onOpen,
  onToggleSelect,
  onTogglePin,
  onToggleArchive,
}: {
  title: string;
  sessions: Session[];
  activeSessionKey: string | null;
  selectedSessionKeys: string[];
  pinnedSessionKeys: string[];
  selecting: boolean;
  onOpen: (sessionKey: string) => void;
  onToggleSelect: (sessionKey: string) => void;
  onTogglePin: (sessionKey: string) => void;
  onToggleArchive: (sessionKey: string, archived: boolean) => void;
}) {
  if (sessions.length === 0) return null;
  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-shell-muted">{title}</div>
        <div className="text-[10px] tabular-nums text-shell-muted/50">{sessions.length}</div>
      </div>
      <div className="space-y-2">
        {sessions.map((session) => (
          <SessionRow
            key={session.key}
            session={session}
            active={activeSessionKey === session.key}
            selected={selectedSessionKeys.includes(session.key)}
            pinned={pinnedSessionKeys.includes(session.key)}
            selecting={selecting}
            onOpen={() => onOpen(session.key)}
            onToggleSelect={() => onToggleSelect(session.key)}
            onTogglePin={() => onTogglePin(session.key)}
            onToggleArchive={() => onToggleArchive(session.key, session.archived)}
          />
        ))}
      </div>
    </section>
  );
}

export function SessionDrawer() {
  const sessions = useAppStore((state) => state.sessions);
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const setActiveSessionKey = useAppStore((state) => state.setActiveSessionKey);
  const draftOpen = useAppStore((state) => state.draftOpen);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);
  const setSessionDrawerOpen = useAppStore((state) => state.setSessionDrawerOpen);
  const sessionDrawerOpen = useAppStore((state) => state.sessionDrawerOpen);
  const sessionSelectMode = useAppStore((state) => state.sessionSelectMode);
  const setSessionSelectMode = useAppStore((state) => state.setSessionSelectMode);
  const selectedSessionKeys = useAppStore((state) => state.selectedSessionKeys);
  const toggleSelectedSessionKey = useAppStore((state) => state.toggleSelectedSessionKey);
  const clearSelectedSessionKeys = useAppStore((state) => state.clearSelectedSessionKeys);
  const setMergeDraft = useAppStore((state) => state.setMergeDraft);
  const upsertSessionState = useAppStore((state) => state.upsertSessionState);
  const pinnedSessionKeys = useAppStore((state) => state.pinnedSessionKeys);
  const togglePinnedSessionKey = useAppStore((state) => state.togglePinnedSessionKey);
  const [query, setQuery] = useState('');
  const [drawerTab, setDrawerTab] = useState<'recent' | 'pinned' | 'archived'>('recent');
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!sessionDrawerOpen) return;
    void wsClient.refreshSessions();
  }, [sessionDrawerOpen]);

  useEffect(() => {
    let cancelled = false;
    const candidates = sessions.map((session) => `${session.key}:${session.updatedAt || ''}`).join('|');
    if (!candidates) return;
    void Promise.all(
      sessions.map(async (session) => {
        const state = await wsClient.resolveSessionState(session.key);
        return state ? [session.key, state] as const : null;
      }),
    )
      .then((records) => {
        if (cancelled) return;
        for (const record of records) {
          if (record) upsertSessionState(record[1]);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [sessions.map((session) => `${session.key}:${session.updatedAt || ''}`).join('|'), upsertSessionState]);

  useEffect(() => {
    if (!sessionDrawerOpen) return;
    const timer = window.setTimeout(() => searchRef.current?.focus(), 0);
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setSessionDrawerOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [sessionDrawerOpen, setSessionDrawerOpen]);

  useEffect(() => {
    if (!sessionDrawerOpen) return;
    const handleMouseDown = (event: MouseEvent) => {
      if (drawerRef.current && !drawerRef.current.contains(event.target as Node)) {
        setSessionDrawerOpen(false);
      }
    };
    document.addEventListener('mousedown', handleMouseDown);
    return () => document.removeEventListener('mousedown', handleMouseDown);
  }, [sessionDrawerOpen, setSessionDrawerOpen]);

  const sections = useMemo(
    () => organizeSessionDrawerSections({ sessions, pinnedSessionKeys, query }),
    [pinnedSessionKeys, query, sessions],
  );

  const closeDrawerAndThen = (fn: () => void) => {
    setSessionDrawerOpen(false);
    if (typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function') {
      window.requestAnimationFrame(() => fn());
      return;
    }
    window.setTimeout(fn, 0);
  };

  const handleNewSession = () => {
    closeDrawerAndThen(() => {
      clearSelectedSessionKeys();
      setSessionSelectMode(false);
      setMergeDraft(null);
      wsClient.beginDraft();
    });
  };

  const handleSessionOpen = (sessionKey: string) => {
    closeDrawerAndThen(() => {
      setDraftOpen(false);
      setMergeDraft(null);
      useAppStore.getState().setInspectorTarget(null);
      setActiveSessionKey(sessionKey);
    });
  };

  const handleArchiveToggle = (sessionKey: string, archived: boolean) => {
    void wsClient.archiveSession(sessionKey, !archived);
    if (!archived && activeSessionKey === sessionKey) {
      setActiveSessionKey(null);
    }
  };

  const handleMergeIntoWorkspace = () => {
    if (selectedSessionKeys.length < 2) return;
    closeDrawerAndThen(() => {
      setMergeDraft({ sourceSessionKeys: selectedSessionKeys });
      setDraftOpen(true);
      setActiveSessionKey(null);
      setSessionSelectMode(false);
      clearSelectedSessionKeys();
      useAppStore.getState().setInspectorTarget(null);
    });
  };

  if (!sessionDrawerOpen) return null;

  return (
    <>
      <div className="absolute inset-0 z-30 bg-shell-bg/20 backdrop-blur-[1px]" aria-hidden="true" />
      <aside className="pointer-events-none absolute inset-y-3 left-3 z-40 flex w-[380px] max-w-[calc(100%-1.5rem)]">
        <div ref={drawerRef} className="pointer-events-auto flex h-full w-full flex-col overflow-hidden rounded-[24px] border border-shell-border bg-shell-sidebar shadow-shell-xl">
          <div className="border-b border-shell-border px-4 pb-3 pt-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[15px] font-semibold text-shell-text">Resume Session</div>
                <div className="mt-1 text-[12px] text-shell-muted">Jump back into any conversation.</div>
              </div>
              <button
                type="button"
                onClick={() => setSessionDrawerOpen(false)}
                className="rounded-xl p-2 text-shell-muted transition-colors hover:bg-shell-panel hover:text-shell-text"
                title="Close session drawer"
                aria-label="Close session drawer"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="mt-4 flex items-center gap-2 rounded-2xl border border-shell-border bg-shell-panel px-3 py-2 transition-colors focus-within:border-shell-accent/35">
              <Search className="h-3.5 w-3.5 text-shell-muted/85" />
              <input
                ref={searchRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                className="min-w-0 flex-1 bg-transparent text-[12px] text-shell-text outline-none placeholder:text-shell-muted/55"
                placeholder="Search sessions..."
                aria-label="Search sessions"
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="rounded-md p-0.5 text-shell-muted/70 transition-colors hover:bg-shell-panel-strong hover:text-shell-text"
                  title="Clear"
                  aria-label="Clear search"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </div>

            <div className="mt-4 flex items-center gap-2">
              <button
                type="button"
                onClick={handleNewSession}
                className="inline-flex items-center gap-1.5 rounded-xl bg-shell-accent px-3 py-2 text-[11px] font-semibold text-shell-bg"
              >
                <Plus className="h-3.5 w-3.5" />
                New
              </button>
              {drawerTab !== 'archived' && (
                <button
                  type="button"
                  onClick={() => {
                    const next = !sessionSelectMode;
                    setSessionSelectMode(next);
                    if (!next) clearSelectedSessionKeys();
                  }}
                  className={`inline-flex items-center gap-1.5 rounded-xl border px-3 py-2 text-[11px] font-semibold transition-colors ${sessionSelectMode ? 'border-shell-accent/30 bg-shell-accent-soft text-shell-accent' : 'border-shell-border bg-shell-panel text-shell-muted hover:text-shell-text'}`}
                >
                  {sessionSelectMode ? <CheckSquare className="h-3.5 w-3.5" /> : <Square className="h-3.5 w-3.5" />}
                  Select
                </button>
              )}
              {sessionSelectMode && drawerTab !== 'archived' && (
                <button
                  type="button"
                  onClick={handleMergeIntoWorkspace}
                  disabled={selectedSessionKeys.length < 2}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-shell-accent/25 bg-shell-accent-soft px-3 py-2 text-[11px] font-semibold text-shell-accent disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <GitMerge className="h-3.5 w-3.5" />
                  Merge
                </button>
              )}
            </div>

            <div className="mt-4 flex items-center gap-2 text-[11px] font-semibold">
              {([
                ['recent', 'Recent'],
                ['pinned', 'Pinned'],
                ['archived', 'Archived'],
              ] as const).map(([id, label]) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => setDrawerTab(id)}
                  className={`rounded-full px-3 py-1.5 transition-colors ${drawerTab === id ? 'bg-shell-accent-soft text-shell-accent' : 'text-shell-muted hover:bg-shell-panel hover:text-shell-text'}`}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto px-3 py-3">
            {draftOpen && drawerTab !== 'archived' && (
              <div className="mb-3 rounded-2xl border border-shell-accent/18 bg-shell-accent-soft px-3 py-2.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-[13px] font-semibold text-shell-text">New Draft Session</span>
                  <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-shell-accent">Draft</span>
                </div>
                <div className="mt-1 text-[11px] text-shell-muted">Configure runtime, then send.</div>
              </div>
            )}

            <div className="space-y-4">
              {drawerTab === 'pinned' && (
                <SessionSection
                  title="Pinned"
                  sessions={sections.pinned}
                  activeSessionKey={activeSessionKey}
                  selectedSessionKeys={selectedSessionKeys}
                  pinnedSessionKeys={pinnedSessionKeys}
                  selecting={sessionSelectMode}
                  onOpen={handleSessionOpen}
                  onToggleSelect={toggleSelectedSessionKey}
                  onTogglePin={togglePinnedSessionKey}
                  onToggleArchive={handleArchiveToggle}
                />
              )}

              {drawerTab === 'recent' && (
                <>
                  <SessionSection
                    title="Pinned"
                    sessions={sections.pinned}
                    activeSessionKey={activeSessionKey}
                    selectedSessionKeys={selectedSessionKeys}
                    pinnedSessionKeys={pinnedSessionKeys}
                    selecting={sessionSelectMode}
                    onOpen={handleSessionOpen}
                    onToggleSelect={toggleSelectedSessionKey}
                    onTogglePin={togglePinnedSessionKey}
                    onToggleArchive={handleArchiveToggle}
                  />
                  <SessionSection
                    title="Today"
                    sessions={sections.recent.today}
                    activeSessionKey={activeSessionKey}
                    selectedSessionKeys={selectedSessionKeys}
                    pinnedSessionKeys={pinnedSessionKeys}
                    selecting={sessionSelectMode}
                    onOpen={handleSessionOpen}
                    onToggleSelect={toggleSelectedSessionKey}
                    onTogglePin={togglePinnedSessionKey}
                    onToggleArchive={handleArchiveToggle}
                  />
                  <SessionSection
                    title="This Week"
                    sessions={sections.recent.thisWeek}
                    activeSessionKey={activeSessionKey}
                    selectedSessionKeys={selectedSessionKeys}
                    pinnedSessionKeys={pinnedSessionKeys}
                    selecting={sessionSelectMode}
                    onOpen={handleSessionOpen}
                    onToggleSelect={toggleSelectedSessionKey}
                    onTogglePin={togglePinnedSessionKey}
                    onToggleArchive={handleArchiveToggle}
                  />
                  <SessionSection
                    title="Earlier"
                    sessions={sections.recent.earlier}
                    activeSessionKey={activeSessionKey}
                    selectedSessionKeys={selectedSessionKeys}
                    pinnedSessionKeys={pinnedSessionKeys}
                    selecting={sessionSelectMode}
                    onOpen={handleSessionOpen}
                    onToggleSelect={toggleSelectedSessionKey}
                    onTogglePin={togglePinnedSessionKey}
                    onToggleArchive={handleArchiveToggle}
                  />
                </>
              )}

              {drawerTab === 'archived' && (
                <SessionSection
                  title="Archived"
                  sessions={sections.archived}
                  activeSessionKey={activeSessionKey}
                  selectedSessionKeys={selectedSessionKeys}
                  pinnedSessionKeys={pinnedSessionKeys}
                  selecting={false}
                  onOpen={handleSessionOpen}
                  onToggleSelect={toggleSelectedSessionKey}
                  onTogglePin={togglePinnedSessionKey}
                  onToggleArchive={handleArchiveToggle}
                />
              )}

              {drawerTab === 'recent' && sections.pinned.length === 0 && sections.recent.today.length === 0 && sections.recent.thisWeek.length === 0 && sections.recent.earlier.length === 0 && (
                <div className="rounded-2xl border border-dashed border-shell-border px-4 py-8 text-center text-[12px] text-shell-muted">
                  No matching active sessions yet.
                </div>
              )}

              {drawerTab === 'pinned' && sections.pinned.length === 0 && (
                <div className="rounded-2xl border border-dashed border-shell-border px-4 py-8 text-center text-[12px] text-shell-muted">
                  Pin the sessions you revisit the most and they&apos;ll live here.
                </div>
              )}

              {drawerTab === 'archived' && sections.archived.length === 0 && (
                <div className="rounded-2xl border border-dashed border-shell-border px-4 py-8 text-center text-[12px] text-shell-muted">
                  No archived sessions yet.
                </div>
              )}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
