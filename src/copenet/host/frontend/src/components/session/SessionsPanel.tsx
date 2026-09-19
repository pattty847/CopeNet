import React, { useEffect, useMemo, useRef, useState } from 'react';
import { GitMerge, PanelLeftClose, Plus, Search, Square } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { wsClient } from '../../lib/wsClient';
import { organizeSessionDrawerSections } from '../../lib/sessionDrawer';
import {
  buildFilters,
  buildSessionRow,
  groupRowsByArea,
  matchesFilter,
  type SessionFilterId,
  type SessionRowModel,
} from '../../runtime/sessionStanding';
import type { Session } from '../../types/backend';
import { SessionStandingRow } from './SessionStandingRow';

/**
 * The session list, as a panel that stays open beside the nav rail.
 *
 * It used to be a popup drawer over the workspace, which meant you could not watch a
 * thread while working in another one — the exact case this list exists for. It is a
 * column now: it pushes content rather than covering it, and it updates in place.
 *
 * Visually it is flat on the page, not a stack of cards: the rows carry their own
 * three-line rhythm (runtime/sessionStanding.ts) and a card border around each one
 * fights that, which is what made the first pass read as cramped.
 */
export function SessionsPanel({ embedded = false, onNavigate }: { embedded?: boolean; onNavigate?: () => void }) {
  const sessions = useAppStore((state) => state.sessions);
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const setActiveSessionKey = useAppStore((state) => state.setActiveSessionKey);
  const draftOpen = useAppStore((state) => state.draftOpen);
  const setDraftOpen = useAppStore((state) => state.setDraftOpen);
  const setSessionsPanelOpen = useAppStore((state) => state.setSessionsPanelOpen);
  const sessionSelectMode = useAppStore((state) => state.sessionSelectMode);
  const setSessionSelectMode = useAppStore((state) => state.setSessionSelectMode);
  const selectedSessionKeys = useAppStore((state) => state.selectedSessionKeys);
  const toggleSelectedSessionKey = useAppStore((state) => state.toggleSelectedSessionKey);
  const clearSelectedSessionKeys = useAppStore((state) => state.clearSelectedSessionKeys);
  const setMergeDraft = useAppStore((state) => state.setMergeDraft);
  const pinnedSessionKeys = useAppStore((state) => state.pinnedSessionKeys);
  const togglePinnedSessionKey = useAppStore((state) => state.togglePinnedSessionKey);
  const sessionStanding = useAppStore((state) => state.sessionStanding);
  const activeRunsBySession = useAppStore((state) => state.activeRunsBySession);
  const liveToolCallsByRun = useAppStore((state) => state.liveToolCallsByRun);

  const [query, setQuery] = useState('');
  const [tab, setTab] = useState<'recent' | 'pinned' | 'archived'>('recent');
  const [activeFilter, setActiveFilter] = useState<SessionFilterId>('all');
  const searchRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    void wsClient.refreshSessions();
  }, [tab]);

  const sections = useMemo(
    () => organizeSessionDrawerSections({ sessions, pinnedSessionKeys, query }),
    [pinnedSessionKeys, query, sessions],
  );

  // One derivation per session per render, shared by the grouping, the chips and the rows.
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
  const rowFor = (session: Session) => rowsByKey.get(session.key) || buildSessionRow(session, undefined, []);

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

  const handleNewSession = () => {
    clearSelectedSessionKeys();
    setSessionSelectMode(false);
    setMergeDraft(null);
    // The Chat|Fleet toggle is the context: New in Fleet mode means a new Fleet room.
    if (useAppStore.getState().agentsWorkspaceMode === 'fleet') {
      useAppStore.getState().setFleetCreateOpen(true);
    } else {
      wsClient.beginDraft();
    }
    onNavigate?.();
  };

  const handleSessionOpen = (sessionKey: string) => {
    if (sessionSelectMode) {
      toggleSelectedSessionKey(sessionKey);
      return;
    }
    setDraftOpen(false);
    setMergeDraft(null);
    useAppStore.getState().setInspectorTarget(null);
    useAppStore.getState().setAgentsWorkspaceMode('chat');
    setActiveSessionKey(sessionKey);
    onNavigate?.();
  };

  const handleArchiveToggle = (sessionKey: string, archived: boolean) => {
    void wsClient.archiveSession(sessionKey, !archived);
    if (!archived && activeSessionKey === sessionKey) setActiveSessionKey(null);
  };

  const handleMergeIntoWorkspace = () => {
    if (selectedSessionKeys.length < 2) return;
    setMergeDraft({ sourceSessionKeys: selectedSessionKeys });
    setDraftOpen(true);
    setActiveSessionKey(null);
    setSessionSelectMode(false);
    clearSelectedSessionKeys();
    useAppStore.getState().setInspectorTarget(null);
    onNavigate?.();
  };

  const groups =
    tab === 'recent'
      ? [...(sections.pinned.length ? [{ area: 'pinned', sessions: sections.pinned }] : []), ...areaGroups]
      : tab === 'pinned'
      ? [{ area: 'pinned', sessions: sections.pinned }]
      : [{ area: 'archived', sessions: sections.archived }];
  const isEmpty = groups.every((group) => group.sessions.length === 0);

  return (
    <aside
      className={`flex h-full min-h-0 flex-col bg-operator-bg text-operator-text ${
        embedded ? 'w-full' : 'w-[340px] shrink-0 border-r border-operator-border'
      }`}
    >
      {/* Header */}
      <div className="shrink-0 border-b border-operator-border px-3 pb-2.5 pt-3">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-baseline gap-2">
            <span className="text-[10px] font-semibold uppercase tracking-[0.22em] text-operator-accent">Sessions</span>
            <span className="text-[10px] tabular-nums text-operator-muted/60">{sessions.length}</span>
          </div>
          {!embedded && (
            <button
              type="button"
              onClick={() => setSessionsPanelOpen(false)}
              className="-mr-1 rounded p-1 text-operator-muted transition-colors hover:text-operator-accent"
              title="Close sessions"
              aria-label="Close sessions"
            >
              <PanelLeftClose className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        <label className="mt-2.5 flex items-center gap-2 rounded-md border border-operator-border bg-operator-panel px-2 py-1.5 transition-colors focus-within:border-operator-accent/35">
          <Search className="h-3 w-3 shrink-0 text-operator-muted" />
          <input
            ref={searchRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="min-w-0 flex-1 bg-transparent text-[11px] text-operator-text outline-none placeholder:text-operator-muted/60"
            placeholder="Search sessions, files, tickers"
          />
        </label>

        <div className="mt-2 flex items-center gap-1.5">
          {sessionSelectMode ? (
            <>
              <button
                type="button"
                onClick={handleMergeIntoWorkspace}
                disabled={selectedSessionKeys.length < 2}
                className="flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-md bg-operator-accent py-1.5 text-[11px] font-semibold text-operator-bg disabled:cursor-not-allowed disabled:opacity-40"
              >
                <GitMerge className="h-3.5 w-3.5" />
                Merge
              </button>
              <button
                type="button"
                onClick={() => {
                  setSessionSelectMode(false);
                  clearSelectedSessionKeys();
                }}
                className="rounded-md border border-operator-border px-2.5 py-1.5 text-[11px] font-semibold text-operator-muted transition-colors hover:text-operator-text"
              >
                {selectedSessionKeys.length} selected
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={handleNewSession}
                className="flex min-w-0 flex-1 items-center justify-center gap-1.5 rounded-md bg-operator-accent py-1.5 text-[11px] font-semibold text-operator-bg"
              >
                <Plus className="h-3.5 w-3.5" />
                New
              </button>
              <button
                type="button"
                onClick={() => setSessionSelectMode(true)}
                className="flex items-center gap-1.5 rounded-md border border-operator-border px-2.5 py-1.5 text-[11px] font-semibold text-operator-muted transition-colors hover:text-operator-accent"
                title="Select sessions to merge"
              >
                <Square className="h-3 w-3" />
                Select
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex shrink-0 border-b border-operator-border text-[10px] font-semibold tracking-wider">
        {(
          [
            ['recent', 'RECENT'],
            ['pinned', 'PINNED'],
            ['archived', 'ARCHIVED'],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`flex-1 py-1.5 text-center transition-colors duration-150 ${
              tab === id
                ? 'border-b-2 border-operator-accent bg-operator-panel/40 text-operator-accent'
                : 'text-operator-muted hover:text-operator-text'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* State chips — only for the live list, and only when they match something. */}
      {tab === 'recent' && filters.length > 1 && (
        <div className="flex shrink-0 flex-wrap items-center gap-1 border-b border-operator-border px-3 py-2 text-[9.5px] font-semibold">
          {filters.map((chip) => (
            <button
              key={chip.id}
              type="button"
              onClick={() => setActiveFilter(chip.id)}
              className={`rounded-full border px-2 py-[3px] transition-colors ${
                activeFilter === chip.id
                  ? 'border-operator-accent/30 bg-operator-accent/10 text-operator-accent'
                  : 'border-operator-border text-operator-muted hover:text-operator-text'
              }`}
            >
              {chip.label} <span className="tabular-nums opacity-70">{chip.count}</span>
            </button>
          ))}
        </div>
      )}

      {/* List */}
      <div className="min-h-0 flex-1 overflow-y-auto pb-3">
        {draftOpen && tab !== 'archived' && (
          <div className="flex flex-col gap-0.5 border-y border-operator-accent/20 px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-[12.5px] font-semibold text-operator-text">New Draft Session</span>
              <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">Draft</span>
            </div>
            <div className="text-[11px] text-operator-muted">Configure runtime, then send.</div>
          </div>
        )}

        {groups.map((group) =>
          group.sessions.length === 0 ? null : (
            <div key={group.area}>
              <div className="flex items-center gap-2 px-3 pb-1.5 pt-3">
                <span
                  className={`font-mono text-[9.5px] font-semibold uppercase tracking-[0.1em] ${
                    group.area === 'nothing changed' ? 'text-operator-muted/75' : 'text-operator-accent'
                  }`}
                >
                  {group.area}
                </span>
                <span className="h-px flex-grow bg-operator-border" />
                <span className="text-[9.5px] tabular-nums text-operator-muted/50">{group.sessions.length}</span>
              </div>
              {group.sessions.map((session) => (
                <SessionStandingRow
                  key={session.key}
                  row={rowFor(session)}
                  age={session.updatedAt || session.createdAt}
                  active={activeSessionKey === session.key}
                  selected={selectedSessionKeys.includes(session.key)}
                  selectMode={sessionSelectMode}
                  archived={session.archived}
                  pinned={pinnedSessionKeys.includes(session.key)}
                  onSelect={() => handleSessionOpen(session.key)}
                  onTogglePin={() => togglePinnedSessionKey(session.key)}
                  onArchiveToggle={(event) => {
                    event.stopPropagation();
                    handleArchiveToggle(session.key, session.archived);
                  }}
                />
              ))}
            </div>
          ),
        )}

        {isEmpty && (
          <div className="px-4 py-10 text-center text-[12px] leading-relaxed text-operator-muted">
            {tab === 'archived'
              ? 'No archived sessions yet.'
              : tab === 'pinned'
              ? 'Pin the sessions you revisit the most and they’ll live here.'
              : recentSessions.length > 0
              ? 'No sessions in that state right now.'
              : 'No saved sessions yet. Start a draft and send your first message.'}
          </div>
        )}
      </div>
    </aside>
  );
}
