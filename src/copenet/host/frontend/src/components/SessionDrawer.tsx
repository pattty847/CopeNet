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
import { buildFilters, buildSessionRow, groupRowsByArea, matchesFilter, type SessionFilterId, type SessionRowModel } from '../runtime/sessionStanding';
import { SessionStateIcon } from './session/SessionStateIcon';
import { formatSessionAge } from '../lib/formatting';
import type { Session } from '../types/backend';

function compactModelName(model?: string | null) {
  if (!model) return '';
  const normalized = model.trim();
  if (!normalized) return '';
  if (normalized.length <= 18) return normalized;
  return `${normalized.slice(0, 16)}…`;
}

function SessionRow({
  session,
  row,
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
  row: SessionRowModel;
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
  const providerName = providers.find((provider) => provider.id === session.provider)?.displayName || session.provider;
  const modelLabel = compactModelName(session.model);

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
              <div className="flex items-start gap-2">
                <SessionStateIcon state={row.state} phase={row.phase} />
                <div className="line-clamp-2 min-w-0 flex-1 text-[13px] font-semibold leading-[1.3] text-shell-text" title={row.title}>
                  {row.title}
                </div>
              </div>
              {row.line ? (
                <div className="mt-1 grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-2 text-[10px] text-shell-muted/85">
                  <div className="min-w-0 truncate" title={row.line}>{row.line}</div>
                  {row.offerClose ? (
                    <span className="rounded border border-shell-accent/35 px-[5px] py-[1px] text-[9.5px] font-semibold text-shell-accent">
                      close?
                    </span>
                  ) : (
                    <span className="tabular-nums text-shell-muted/50">
                      {row.phase === 'settled' ? formatSessionAge(session.updatedAt || session.createdAt) : 'now'}
                    </span>
                  )}
                </div>
              ) : null}
              {row.ledger || row.tags.length > 0 ? (
                <div className="mt-1 flex items-center gap-[7px] font-mono text-[9.5px] text-shell-muted/85">
                  {row.ledger ? (
                    <>
                      {row.ledger.added > 0 && <span className="text-operator-success">+{row.ledger.added}</span>}
                      {row.ledger.removed > 0 && <span className="text-operator-error">&minus;{row.ledger.removed}</span>}
                      {row.ledger.files.map((file) => (
                        <span key={file} className="truncate">{file}</span>
                      ))}
                      {row.ledger.moreFiles > 0 && <span className="text-shell-muted/50">+{row.ledger.moreFiles}</span>}
                    </>
                  ) : null}
                  {row.tags.length > 0 ? (
                    <span className="ml-auto flex shrink-0 items-center gap-[4px]">
                      {row.tags.map((tag) => (
                        <span
                          key={tag.label}
                          className={`rounded border px-[5px] py-[1.5px] text-[8.5px] ${
                            tag.tone === 'alert'
                              ? 'border-operator-error/40 text-operator-error'
                              : 'border-shell-accent/35 text-shell-accent'
                          }`}
                        >
                          {tag.label}
                        </span>
                      ))}
                    </span>
                  ) : null}
                </div>
              ) : null}
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
  rowFor,
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
  rowFor: (session: Session) => SessionRowModel;
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
            row={rowFor(session)}
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
  const pinnedSessionKeys = useAppStore((state) => state.pinnedSessionKeys);
  const togglePinnedSessionKey = useAppStore((state) => state.togglePinnedSessionKey);
  const [query, setQuery] = useState('');
  const [drawerTab, setDrawerTab] = useState<'recent' | 'pinned' | 'archived'>('recent');
  const [activeFilter, setActiveFilter] = useState<SessionFilterId>('all');
  const drawerRef = useRef<HTMLDivElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    if (!sessionDrawerOpen) return;
    void wsClient.refreshSessions();
  }, [sessionDrawerOpen]);

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

  // One derivation per session per render (runtime/sessionStanding.ts), shared by the
  // grouping, the filter chips and each row.
  const sessionStanding = useAppStore((state) => state.sessionStanding);
  const activeRunsBySession = useAppStore((state) => state.activeRunsBySession);
  const liveToolCallsByRun = useAppStore((state) => state.liveToolCallsByRun);
  const rowsByKey = useMemo(() => {
    const map = new Map<string, SessionRowModel>();
    for (const session of sessions) {
      const runId = activeRunsBySession[session.key];
      map.set(
        session.key,
        buildSessionRow(session, sessionStanding[session.key], runId ? liveToolCallsByRun[runId] || [] : []),
      );
    }
    return map;
  }, [sessions, sessionStanding, activeRunsBySession, liveToolCallsByRun]);
  const rowFor = (session: Session) =>
    rowsByKey.get(session.key) || buildSessionRow(session, undefined, []);

  // The Recent tab groups by the area the work lives in, not by clock: you remember a
  // thread by where it was, and the chips answer "what still needs me".
  const recentSessions = useMemo(
    () => [...sections.recent.today, ...sections.recent.thisWeek, ...sections.recent.earlier],
    [sections],
  );
  const filters = useMemo(() => buildFilters(recentSessions.map(rowFor)), [recentSessions, rowsByKey]);
  const visibleRecent = useMemo(
    () => recentSessions.filter((session) => matchesFilter(rowFor(session), activeFilter)),
    [recentSessions, rowsByKey, activeFilter],
  );
  const areaGroups = useMemo(() => {
    const byKey = new Map(visibleRecent.map((session) => [session.key, session]));
    return groupRowsByArea(visibleRecent.map(rowFor)).map((group) => ({
      area: group.area,
      sessions: group.rows.map((row) => byKey.get(row.sessionKey)).filter((item): item is Session => Boolean(item)),
    }));
  }, [visibleRecent, rowsByKey]);

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
      // The Chat|Fleet toggle is the context: New in Fleet mode means a new
      // Fleet room (the create screen handles archiving the current one).
      if (useAppStore.getState().agentsWorkspaceMode === 'fleet') {
        useAppStore.getState().setFleetCreateOpen(true);
      } else {
        wsClient.beginDraft();
      }
    });
  };

  const handleSessionOpen = (sessionKey: string) => {
    closeDrawerAndThen(() => {
      setDraftOpen(false);
      setMergeDraft(null);
      useAppStore.getState().setInspectorTarget(null);
      useAppStore.getState().setAgentsWorkspaceMode('chat');
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
        <div ref={drawerRef} className="pointer-events-auto flex h-full w-full flex-col overflow-hidden rounded-xl border border-shell-border bg-shell-sidebar shadow-shell-xl">
          <div className="border-b border-shell-border px-4 pb-3 pt-4">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-[15px] font-semibold text-shell-text">Sessions</div>
                <div className="mt-1 text-[12px] text-shell-muted">Where every thread stands.</div>
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

            {drawerTab === 'recent' && filters.length > 1 && (
              <div className="mt-2 flex flex-wrap items-center gap-1.5 text-[10px] font-semibold">
                {filters.map((chip) => (
                  <button
                    key={chip.id}
                    type="button"
                    onClick={() => setActiveFilter(chip.id)}
                    className={`rounded-full border px-2 py-1 transition-colors ${
                      activeFilter === chip.id
                        ? 'border-shell-accent/30 bg-shell-accent-soft text-shell-accent'
                        : 'border-shell-border text-shell-muted hover:text-shell-text'
                    }`}
                  >
                    {chip.label} <span className="tabular-nums opacity-70">{chip.count}</span>
                  </button>
                ))}
              </div>
            )}
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
                  rowFor={rowFor}
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
                    rowFor={rowFor}
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
                  {areaGroups.map((group) => (
                    <SessionSection
                      key={group.area}
                      title={group.area}
                      rowFor={rowFor}
                      sessions={group.sessions}
                      activeSessionKey={activeSessionKey}
                      selectedSessionKeys={selectedSessionKeys}
                      pinnedSessionKeys={pinnedSessionKeys}
                      selecting={sessionSelectMode}
                      onOpen={handleSessionOpen}
                      onToggleSelect={toggleSelectedSessionKey}
                      onTogglePin={togglePinnedSessionKey}
                      onToggleArchive={handleArchiveToggle}
                    />
                  ))}
                </>
              )}

              {drawerTab === 'archived' && (
                <SessionSection
                  title="Archived"
                  rowFor={rowFor}
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

              {drawerTab === 'recent' && sections.pinned.length === 0 && areaGroups.length === 0 && (
                <div className="rounded-2xl border border-dashed border-shell-border px-4 py-8 text-center text-[12px] text-shell-muted">
                  {recentSessions.length > 0
                    ? 'No sessions in that state right now.'
                    : 'No matching active sessions yet.'}
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
