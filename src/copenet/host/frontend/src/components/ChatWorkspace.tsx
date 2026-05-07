import React, { useEffect, useMemo, useRef, useState, KeyboardEvent } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { MessageBubble } from './MessageBubble';
import { WorkingSetCard } from './runtime/WorkingSetCard';
import { PausedRunBanner } from './PausedRunBanner';
import { Archive, ArrowDown, ArrowUp, CopyPlus, Download, Ellipsis, GitMerge, Mic, Paperclip, Send, Sparkles, X } from 'lucide-react';
import { ConversationDebugActions } from './ConversationDebugActions';
import { PERSONAL_STARTER_PRESETS, shouldRenderResumeSnapshot } from '../lib/personalHistory';
import { useIsMobile } from '../lib/responsive';
import type { SessionStateRecord } from '../types/backend';

export function ChatWorkspace() {
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const sessions = useAppStore((state) => state.sessions);
  const messagesMap = useAppStore((state) => state.messages);
  const activeRunId = useAppStore((state) => state.activeRunId);
  const appError = useAppStore((state) => state.appError);
  const clearAppError = useAppStore((state) => state.clearAppError);
  const setAppError = useAppStore((state) => state.setAppError);
  const draftSettings = useAppStore((state) => state.draftSettings);
  const draftStarterIntent = useAppStore((state) => state.draftStarterIntent);
  const setDraftStarterIntent = useAppStore((state) => state.setDraftStarterIntent);
  const mergeDraft = useAppStore((state) => state.mergeDraft);
  const setMergeDraft = useAppStore((state) => state.setMergeDraft);
  const mergeStates = useAppStore((state) => state.mergeStates);
  const setMergeState = useAppStore((state) => state.setMergeState);
  const draftComposerSeed = useAppStore((state) => state.draftComposerSeed);
  const setDraftComposerSeed = useAppStore((state) => state.setDraftComposerSeed);
  const upsertSessionState = useAppStore((state) => state.upsertSessionState);

  const messages = (activeSessionKey ? messagesMap[activeSessionKey] : undefined) || [];
  const activeSession = sessions.find((session) => session.key === activeSessionKey) || null;
  const activeMergeState = activeSessionKey ? mergeStates[activeSessionKey] || null : null;
  const isDraft = !activeSession;
  const isArchived = Boolean(activeSession?.archived);
  const isMergePrep = Boolean(mergeDraft);
  const composerDisabled = isMergePrep || isArchived || Boolean(activeRunId);
  const canDebugConversation = Boolean(activeSession);
  const isMobile = useIsMobile();
  const activeSessions = sessions.filter((session) => !session.archived).length;
  const archivedSessions = sessions.filter((session) => session.archived).length;
  const connectedProviders = new Set(sessions.filter((session) => !session.archived).map((session) => session.provider).filter(Boolean)).size;

  const [input, setInput] = useState('');
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editTitleValue, setEditTitleValue] = useState('');
  const [actionsOpen, setActionsOpen] = useState(false);
  const [pulseState, setPulseState] = useState<Record<string, unknown> | null>(null);
  const [sessionState, setSessionState] = useState<SessionStateRecord | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const actionsMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (activeSessionKey && messagesMap[activeSessionKey] === undefined) {
      void wsClient.loadHistory(activeSessionKey);
    }
  }, [activeSessionKey, messagesMap]);

  useEffect(() => {
    if (!activeSessionKey) return;
    let cancelled = false;
    setPulseState(null);
    setSessionState(null);
    void wsClient.resolveMergeState(activeSessionKey).then((mergeState) => {
      if (!cancelled) setMergeState(activeSessionKey, mergeState);
    }).catch(() => {
      if (!cancelled) setMergeState(activeSessionKey, null);
    });
    void wsClient.resolveSessionState(activeSessionKey).then((state) => {
      if (!cancelled) {
        setSessionState(state);
        if (state) upsertSessionState(state);
        setPulseState(state?.pulse_state && typeof state.pulse_state === 'object' ? state.pulse_state as Record<string, unknown> : null);
      }
    }).catch(() => {
      if (!cancelled) {
        setSessionState(null);
        setPulseState(null);
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeSessionKey, setMergeState, upsertSessionState]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 84)}px`;
    }
  }, [input]);

  useEffect(() => {
    if (!draftComposerSeed) return;
    setInput((current) => (current.trim() ? current : draftComposerSeed));
    setDraftComposerSeed(null);
  }, [draftComposerSeed, setDraftComposerSeed]);

  useEffect(() => {
    if (!actionsOpen) return;
    const handler = (e: MouseEvent) => {
      if (actionsMenuRef.current && !actionsMenuRef.current.contains(e.target as Node)) {
        setActionsOpen(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [actionsOpen]);

  const handleSend = async () => {
    if (!input.trim() || activeRunId) return;
    try {
      await wsClient.sendMessage(input);
      setInput('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    } catch {
      // user-visible error is already stored
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const handleTitleSave = () => {
    if (!activeSession) return;
    const newTitle = editTitleValue.trim();
    void wsClient.renameSession(activeSession.key, newTitle);
    setIsEditingTitle(false);
  };

  const handleDebugCopy = async () => {
    if (!activeSession) return;
    try {
      clearAppError();
      await wsClient.debugCopySession(activeSession.key);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to create debug copy.');
    }
  };

  const mergeSourceSessions = useMemo(
    () => (mergeDraft?.sourceSessionKeys || []).map((key) => sessions.find((session) => session.key === key)).filter((session): session is NonNullable<typeof activeSession> => Boolean(session)),
    [mergeDraft, sessions],
  );
  const resumeDecisions = useMemo(
    () => (sessionState?.prior_decisions || []).filter((value) => !/^Run .* completed with tool mode /.test(value)).slice(0, 3),
    [sessionState],
  );
  const showResumeSnapshot = Boolean(
    activeSession &&
    sessionState &&
    shouldRenderResumeSnapshot({
      taskSummary: sessionState.task_summary || null,
      unresolvedQuestions: sessionState.unresolved_questions || [],
      priorDecisions: resumeDecisions,
      starterIntent: sessionState.starter_intent || null,
    }),
  );

  const handleExportConversation = async () => {
    if (!activeSession) return;
    try {
      clearAppError();
      const exported = await wsClient.exportSession(activeSession.key);
      const blob = new Blob([exported.markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${activeSession.key}-conversation.md`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.setTimeout(() => URL.revokeObjectURL(url), 0);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to export conversation.');
    }
  };

  const handleCreatePulse = async () => {
    if (!activeSession) return;
    try {
      clearAppError();
      const pulse = await wsClient.createPulseFromSession({
        sessionKey: activeSession.key,
        provider: draftSettings.provider || activeSession.provider,
        model: draftSettings.model || activeSession.model || '',
        systemPromptId: draftSettings.systemPromptId || activeSession.systemPromptId || 'default',
        taskPromptId: draftSettings.taskPromptId || activeSession.taskPromptId || 'none',
      });
      useAppStore.getState().upsertPulse(pulse);
      useAppStore.getState().setRightPanelTab('inbox');
      useAppStore.getState().setRightPanelOpen(true);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to create pulse.');
    }
  };

  const applyPromptSeed = (seed: string) => {
    setInput(seed);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  };

  const handleStarterIntent = (intentId: typeof PERSONAL_STARTER_PRESETS[number]['id'], seed: string) => {
    setDraftStarterIntent({ id: intentId });
    applyPromptSeed(seed);
  };

  const updateMergeDraftKeys = (keys: string[]) => {
    if (keys.length < 2) {
      setMergeDraft(null);
      return;
    }
    setMergeDraft({ sourceSessionKeys: keys });
  };

  const moveMergeSource = (fromIndex: number, delta: -1 | 1) => {
    if (!mergeDraft) return;
    const toIndex = fromIndex + delta;
    if (toIndex < 0 || toIndex >= mergeDraft.sourceSessionKeys.length) return;
    const next = [...mergeDraft.sourceSessionKeys];
    const [moved] = next.splice(fromIndex, 1);
    next.splice(toIndex, 0, moved);
    updateMergeDraftKeys(next);
  };

  const removeMergeSource = (sessionKey: string) => {
    if (!mergeDraft) return;
    updateMergeDraftKeys(mergeDraft.sourceSessionKeys.filter((key) => key !== sessionKey));
  };

  const handleCreateMergedWorkspace = async () => {
    if (!mergeDraft || mergeDraft.sourceSessionKeys.length < 2 || activeRunId) return;
    const draft = draftSettings;
    try {
      clearAppError();
      const created = await wsClient.createMergedSession({
        sourceSessionKeys: mergeDraft.sourceSessionKeys,
        provider: draft.provider,
        model: draft.model,
        systemPromptId: draft.systemPromptId,
        taskPromptId: draft.taskPromptId,
        workspaceRoot: draft.workspaceRoot || '',
      });
      useAppStore.getState().upsertSession(created.session);
      useAppStore.getState().setActiveSessionKey(created.session.key);
      useAppStore.getState().setDraftOpen(false);
      setMergeDraft(null);
      setInput('');
      setMergeState(created.session.key, created.mergeState);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to create merged workspace.');
    }
  };

  return (
    <main className="flex-1 flex flex-col bg-operator-bg relative h-full overflow-hidden">
      {/* Run-in-progress accent bar */}
      {activeRunId && (
        <div className="run-progress-bar h-[2px] w-full bg-operator-accent/10" />
      )}

      {/* Paused-run approval banner */}
      <PausedRunBanner />

      {/* Header */}
      <div className="border-b border-operator-border bg-operator-bg flex flex-col">
        <div className={`flex gap-2.5 sm:px-4 sm:py-2.5 ${isMobile ? 'items-start justify-between px-3 py-2' : 'px-3 py-2.5 items-center justify-between'}`}>
          <div className="flex-1 min-w-0">
            {/* Title */}
            {isEditingTitle ? (
              <input
                autoFocus
                value={editTitleValue}
                onChange={(e) => setEditTitleValue(e.target.value)}
                onBlur={handleTitleSave}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleTitleSave();
                  if (e.key === 'Escape') setIsEditingTitle(false);
                }}
                className="bg-operator-panel border border-operator-accent outline-none font-semibold text-[17px] text-operator-text w-full max-w-md rounded-lg px-2 py-1 -ml-2 font-sans"
              />
            ) : (
              <h1
                className={`font-semibold ${isMobile ? 'text-[15px]' : 'text-[17px]'} text-operator-text font-sans truncate ${activeSession ? 'cursor-pointer hover:text-operator-accent transition-colors duration-150' : ''}`}
                onClick={() => {
                  if (!activeSession) return;
                  setEditTitleValue(activeSession.title || '');
                  setIsEditingTitle(true);
                }}
                title={activeSession ? 'Click to edit title' : undefined}
              >
                {activeSession?.title || (mergeDraft ? 'Merge Workspace' : 'New Chat')}
              </h1>
            )}

            {activeSession?.archived && (
              <div className="mt-1.5">
                <span className="px-2 py-0.5 rounded-md border border-operator-error/25 bg-operator-error/8 text-[10px] font-semibold uppercase tracking-wider text-operator-error">
                  Archived
                </span>
              </div>
            )}
          </div>

          {/* Actions */}
          <div className={`flex shrink-0 items-center ${isMobile ? 'pt-0' : 'ml-3'}`}>
            {isMobile ? (
              <ConversationDebugActions
                disabled={!canDebugConversation}
                compact={true}
                onDebugCopy={handleDebugCopy}
                onExportConversation={handleExportConversation}
                onCreatePulse={activeSession ? handleCreatePulse : undefined}
                onArchiveConversation={activeSession ? () => void wsClient.archiveSession(activeSession.key, !activeSession.archived) : undefined}
              />
            ) : (
              <div className="relative" ref={actionsMenuRef}>
                <button
                  type="button"
                  onClick={() => setActionsOpen((v) => !v)}
                  disabled={!canDebugConversation}
                  className="flex h-7 w-7 items-center justify-center rounded-lg border border-operator-border text-operator-muted hover:text-operator-accent hover:border-operator-accent/30 transition-all duration-150 disabled:opacity-30"
                  title="Session actions"
                >
                  <Ellipsis className="w-3.5 h-3.5" />
                </button>
                {actionsOpen && (
                  <div className="absolute right-0 top-full mt-1.5 w-44 z-20 rounded-xl border border-operator-border bg-operator-panel shadow-lg overflow-hidden py-1">
                    <button
                      type="button"
                      onClick={() => { void handleDebugCopy(); setActionsOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-operator-muted hover:text-operator-text hover:bg-operator-panel/60 transition-colors text-left"
                    >
                      <CopyPlus className="w-3.5 h-3.5 shrink-0" />
                      Debug Copy
                    </button>
                    <button
                      type="button"
                      onClick={() => { void handleExportConversation(); setActionsOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-operator-muted hover:text-operator-text hover:bg-operator-panel/60 transition-colors text-left"
                    >
                      <Download className="w-3.5 h-3.5 shrink-0" />
                      Export
                    </button>
                    <button
                      type="button"
                      onClick={() => { void handleCreatePulse(); setActionsOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-operator-muted hover:text-operator-accent hover:bg-operator-panel/60 transition-colors text-left"
                    >
                      <Sparkles className="w-3.5 h-3.5 shrink-0" />
                      Create Pulse
                    </button>
                    {activeSession && (
                      <button
                        type="button"
                        onClick={() => { void wsClient.archiveSession(activeSession.key, !activeSession.archived); setActionsOpen(false); }}
                        className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-operator-muted hover:text-operator-text hover:bg-operator-panel/60 transition-colors text-left"
                      >
                        <Archive className="w-3.5 h-3.5 shrink-0" />
                        {activeSession.archived ? 'Restore' : 'Archive'}
                      </button>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Error banner */}
      {appError && (
        <div className={`${isMobile ? 'px-3' : 'px-4'} py-1.5 text-[12px] text-operator-error bg-operator-error/8 border-b border-operator-error/20`}>
          {appError}
          <button onClick={clearAppError} className="ml-3 underline text-operator-muted hover:text-operator-text transition-colors duration-150">
            dismiss
          </button>
        </div>
      )}

      {activeSession && activeMergeState && (
        <div className={`${isMobile ? 'px-3 py-2' : 'px-4 py-2'} border-b border-operator-border/70 bg-operator-panel/10`}>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-operator-muted">
            <span className="inline-flex items-center gap-1.5 font-semibold text-operator-text">
              <GitMerge className="h-3.5 w-3.5 text-operator-accent" />
              {activeMergeState.status === 'complete'
                ? 'Merged context ready'
                : activeMergeState.status === 'failed'
                  ? 'Merged context partial'
                  : 'Preparing merged context…'}
            </span>
            <span className="text-operator-muted/60 tabular-nums">
              {activeMergeState.completedSources}/{activeMergeState.totalSources} sources
            </span>
            {activeMergeState.conflicts.length > 0 && (
              <span className="rounded-full border border-operator-error/25 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-operator-error">
                {activeMergeState.conflicts.length} conflict{activeMergeState.conflicts.length === 1 ? '' : 's'}
              </span>
            )}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {activeMergeState.sources.map((source) => (
              <button
                key={source.sessionKey}
                type="button"
                onClick={() => useAppStore.getState().setActiveSessionKey(source.sessionKey)}
                className="rounded-full border border-operator-border px-2 py-1 text-[10px] text-operator-muted transition-colors hover:border-operator-accent/30 hover:text-operator-accent"
                title={source.title || source.sessionKey}
              >
                {source.title || source.sessionKey}
              </button>
            ))}
          </div>
        </div>
      )}

      {activeSession && !activeMergeState && pulseState && (
        <div className={`${isMobile ? 'px-3 py-2' : 'px-4 py-2'} border-b border-operator-border/70 bg-operator-panel/10`}>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-operator-muted">
            <span className="inline-flex items-center gap-1.5 font-semibold text-operator-text">
              <Sparkles className="h-3.5 w-3.5 text-operator-accent" />
              Pulse context ready
            </span>
            {typeof pulseState.why_now === 'string' && pulseState.why_now.trim() && (
              <span className="text-operator-muted/75">{pulseState.why_now}</span>
            )}
          </div>
          {Array.isArray(pulseState.source_session_keys) && pulseState.source_session_keys.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {(pulseState.source_session_keys as unknown[]).map((value) => {
                const sourceKey = String(value || '').trim();
                if (!sourceKey) return null;
                const sourceSession = sessions.find((session) => session.key === sourceKey);
                return (
                  <button
                    key={sourceKey}
                    type="button"
                    onClick={() => useAppStore.getState().setActiveSessionKey(sourceKey)}
                    className="rounded-full border border-operator-border px-2 py-1 text-[10px] text-operator-muted transition-colors hover:border-operator-accent/30 hover:text-operator-accent"
                    title={sourceSession?.title || sourceKey}
                  >
                    {sourceSession?.title || sourceKey}
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {showResumeSnapshot && sessionState && (
        <div className={`${isMobile ? 'px-3 py-2' : 'px-4 py-2'} border-b border-operator-border/70 bg-operator-panel/5`}>
          <div className="flex flex-wrap items-center gap-2 text-[11px] text-operator-muted">
            <span className="font-semibold text-operator-text">Where we left off</span>
            {sessionState.starter_intent && (
              <span className="rounded-full border border-operator-accent/20 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-operator-accent">
                {sessionState.starter_intent.replaceAll('_', ' ')}
              </span>
            )}
          </div>
          <div className="mt-2 grid gap-2 md:grid-cols-3">
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-operator-muted">Current focus</div>
              <div className="mt-1 text-[12px] leading-5 text-operator-text">{sessionState.task_summary || 'Session context is ready.'}</div>
            </div>
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-operator-muted">Open questions</div>
              <div className="mt-1 space-y-1 text-[12px] leading-5 text-operator-text">
                {(sessionState.unresolved_questions || []).slice(0, 2).map((item) => (
                  <div key={item}>• {item}</div>
                ))}
                {(sessionState.unresolved_questions || []).length === 0 && <div className="text-operator-muted">No open questions saved.</div>}
              </div>
            </div>
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-operator-muted">Latest decisions</div>
              <div className="mt-1 space-y-1 text-[12px] leading-5 text-operator-text">
                {resumeDecisions.slice(0, 2).map((item) => (
                  <div key={item}>• {item}</div>
                ))}
                {resumeDecisions.length === 0 && <div className="text-operator-muted">No explicit decisions saved yet.</div>}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Working Set — glanceable, pinned above the message stream */}
      {!isMergePrep && <WorkingSetCard sessionKey={activeSessionKey} isDraft={isDraft} />}

      {/* Messages */}
      <div className={`flex-1 overflow-y-auto ${isMobile ? 'px-3 py-2.5' : 'px-2 py-2.5'}`}>
        {messages.length === 0 ? (
          mergeDraft ? (
            <div className={`mx-auto w-full max-w-3xl ${isMobile ? 'mt-2.5' : 'mt-3'} border border-operator-border/70 border-x-0 px-4 py-4`}>
              <div className="mb-2 inline-flex items-center border border-operator-accent/18 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-operator-accent">
                Merge Workspace
              </div>
              <h2 className={`font-serif text-operator-text ${isMobile ? 'text-[24px] leading-8' : 'text-[30px] leading-[1.08]'}`}>
                Build one fresh agent session from the sessions you want to think across.
              </h2>
              <p className="mt-2.5 max-w-2xl text-[13px] leading-6 text-operator-muted">
                Choose the runtime in the inspector, keep the source list tight, and CopeNet will open the merged session immediately while source summaries stream in.
              </p>

              <div className="mt-4 border-y border-operator-border/60">
                {mergeSourceSessions.map((session, index) => (
                  <div key={session.key} className="flex items-center gap-2 border-b border-operator-border/50 px-0 py-2 last:border-b-0">
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12px] font-semibold text-operator-text">{session.title || session.key}</div>
                      <div className="truncate text-[11px] text-operator-muted">
                        {session.provider} · {session.model || 'default'}
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => moveMergeSource(index, -1)}
                        disabled={index === 0}
                        className="rounded-md border border-operator-border p-1 text-operator-muted transition-colors hover:text-operator-accent disabled:opacity-35"
                        title="Move up"
                      >
                        <ArrowUp className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveMergeSource(index, 1)}
                        disabled={index === mergeSourceSessions.length - 1}
                        className="rounded-md border border-operator-border p-1 text-operator-muted transition-colors hover:text-operator-accent disabled:opacity-35"
                        title="Move down"
                      >
                        <ArrowDown className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeMergeSource(session.key)}
                        className="rounded-md border border-operator-border p-1 text-operator-muted transition-colors hover:text-operator-error"
                        title="Remove source"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-3 text-[11px] text-operator-muted">
                <span className="rounded-full border border-operator-border px-2 py-1">
                  Preparing summaries for {mergeSourceSessions.length} sessions
                </span>
                <span>Runtime comes from the inspector on the right.</span>
              </div>

              <div className="mt-4 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleCreateMergedWorkspace()}
                  disabled={mergeSourceSessions.length < 2 || Boolean(activeRunId)}
                  className="glow-accent inline-flex items-center gap-1.5 rounded-lg bg-operator-accent px-3 py-2 text-[12px] font-semibold text-operator-bg disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <GitMerge className="h-3.5 w-3.5" />
                  Create merged workspace
                </button>
                <button
                  type="button"
                  onClick={() => setMergeDraft(null)}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-operator-border px-3 py-2 text-[12px] font-semibold text-operator-muted transition-colors hover:text-operator-text"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : isDraft ? (
            <div className={`mx-auto w-full max-w-3xl ${isMobile ? 'mt-2.5' : 'mt-3'} border border-operator-border/70 border-x-0 px-4 py-4`}>
              <div className={`grid gap-4 ${isMobile ? 'grid-cols-1' : 'grid-cols-[minmax(0,1.7fr)_minmax(14rem,0.9fr)]'}`}>
                <div>
                  <div className="mb-2 inline-flex items-center border border-operator-accent/18 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-operator-accent">
                    Operator Launchpad
                  </div>
                  <h2 className={`font-serif text-operator-text ${isMobile ? 'text-[24px] leading-8' : 'text-[32px] leading-[1.05]'}`}>
                    Stand up a fresh agent run with a little more intention.
                  </h2>
                  <p className="mt-2.5 max-w-2xl text-[13px] leading-6 text-operator-muted">
                    Pick a runtime in the inspector, seed the composer with a proven opening move, and let the first send lock the session around a real job instead of a blank box.
                  </p>

                  <div className={`mt-4 grid gap-0 ${isMobile ? 'grid-cols-1' : 'grid-cols-3 divide-x divide-operator-border/60 border-y border-operator-border/60'}`}>
                    {[
                      { label: 'Active sessions', value: String(activeSessions), hint: 'Live operator runs' },
                      { label: 'Archived', value: String(archivedSessions), hint: 'Readable handoffs' },
                      { label: 'Connected runtimes', value: String(connectedProviders || 0), hint: 'Providers in rotation' },
                    ].map((item) => (
                      <div key={item.label} className={`px-3 py-2.5 ${isMobile ? 'border-b border-operator-border/60 last:border-b-0' : ''}`}>
                        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-operator-muted">
                          {item.label}
                        </div>
                        <div className="mt-2 text-[28px] font-semibold leading-none text-operator-text">
                          {item.value}
                        </div>
                        <div className="mt-2 text-[11px] text-operator-muted">
                          {item.hint}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="mt-4">
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-operator-muted">
                      Opening Moves
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {[
                        {
                          label: 'Research Scout',
                          seed: 'Inspect the repository with tools, then summarize the architecture, the sharp edges, and the next best moves.',
                        },
                        {
                          label: 'Signal Sweep',
                          seed: 'Review the latest runs, artifacts, and failures, then call out anything anomalous or worth operator attention.',
                        },
                        {
                          label: 'Workflow Draft',
                          seed: 'Turn this objective into a repeatable workflow with checkpoints, dependencies, and clear handoff notes.',
                        },
                      ].map((option) => (
                        <button
                          key={option.label}
                          type="button"
                          onClick={() => applyPromptSeed(option.seed)}
                          className="rounded-full border border-operator-border bg-operator-panel px-3 py-1.5 text-[12px] font-medium text-operator-text transition-colors duration-150 hover:border-operator-accent/35 hover:text-operator-accent"
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="mt-4 border-t border-operator-border/60 pt-4">
                    <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.18em] text-operator-muted">
                      Personal starters
                    </div>
                    <div className="grid gap-2 sm:grid-cols-3">
                      {PERSONAL_STARTER_PRESETS.map((option) => {
                        const active = draftStarterIntent?.id === option.id;
                        return (
                          <button
                            key={option.id}
                            type="button"
                            onClick={() => handleStarterIntent(option.id, option.seed)}
                            className={`rounded-xl border px-3 py-2 text-left transition-colors duration-150 ${
                              active
                                ? 'border-operator-accent/35 bg-operator-accent/8'
                                : 'border-operator-border bg-operator-panel/30 hover:border-operator-accent/28'
                            }`}
                          >
                            <div className="text-[12px] font-semibold text-operator-text">{option.label}</div>
                            <div className="mt-1 text-[11px] leading-5 text-operator-muted">{option.cue}</div>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="border-l border-operator-border/60 pl-4">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-operator-accent">
                    Session Doctrine
                  </div>
                  <div className="mt-2.5 space-y-2.5 text-[12px] leading-6 text-operator-muted">
                    <p>First send creates and locks the session around its provider, model, profile, and mode.</p>
                    <p>Keep the opener concrete. The cleanest sessions start with a bounded objective and an explicit output shape.</p>
                    <p className="text-operator-text">
                      Tonight’s setup is ready whenever you are: choose the runtime, seed the ask, and let the console do the rest.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className={`max-w-lg mx-auto ${isMobile ? 'mt-4' : 'mt-8'} border border-operator-border/60 px-4 py-4 text-center`}>
              <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-accent mb-2">
                {isArchived ? 'Archived Session' : 'Session Ready'}
              </div>
              <div className="text-operator-text font-sans text-[14px] mb-1.5">
                {isArchived ? 'This session is archived. Restore it to continue chatting.' : 'No history loaded for this session yet.'}
              </div>
              <div className="text-operator-muted text-[12px] leading-relaxed">
                {isArchived
                  ? 'Archived sessions stay readable, but input stays disabled until you restore them.'
                  : 'This conversation has not received any assistant output yet.'}
              </div>
            </div>
          )
        ) : (
          <div className="flex flex-col">
            {messages.map((message) => (
              <MessageBubble key={message.localId} message={message} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <div className={`border-t border-operator-border bg-operator-panel/40 ${isMobile ? 'px-3 pb-3 pt-2.5' : 'px-3 py-2.5'}`}>
        <div className="flex items-center justify-between px-1 pb-1 text-[10px] font-semibold uppercase tracking-wider">
          <span className={`${composerDisabled ? 'text-operator-muted/50' : 'text-operator-muted'}`}>
            {isMergePrep
              ? 'Create the merged workspace before sending messages'
              : isArchived
                ? 'Composer disabled for archived sessions'
                : activeRunId
                  ? 'Assistant response in progress'
                  : isDraft
                    ? 'First send creates and locks this session'
                    : 'Session is live and locked to its runtime'}
          </span>
          <span className={(isDraft || isMergePrep) ? 'text-operator-accent' : 'text-operator-success'}>
            {isMergePrep ? 'Merge Prep' : isDraft ? 'Draft' : 'Locked'}
          </span>
        </div>

        <div className={`flex gap-1.5 bg-operator-bg border border-operator-border rounded-lg px-2 py-1.5 focus-within:border-operator-accent/40 transition-colors duration-150 ${isMobile ? 'items-end' : 'items-end'}`}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={composerDisabled}
            placeholder={isMergePrep ? 'Create the merged workspace to begin...' : isArchived ? 'SESSION ARCHIVED' : isDraft ? 'Send the first message to create this session...' : 'Message the agent...'}
            className="flex-1 bg-transparent px-2 py-1 text-[13px] leading-5 font-sans text-operator-text focus:outline-none disabled:opacity-40 resize-none max-h-[84px] overflow-y-auto placeholder:text-operator-muted/50"
            rows={1}
          />

          <div className={`flex items-center gap-0.5 shrink-0 ${isMobile ? 'pb-0' : 'pb-0.5'}`}>
            <button
              disabled={composerDisabled}
              className="p-2 text-operator-muted hover:text-operator-text transition-colors duration-150 disabled:opacity-40 rounded-lg hover:bg-operator-panel"
              title="Attach file"
            >
              <Paperclip className="w-3.5 h-3.5" />
            </button>
            <button
              disabled={composerDisabled}
              className="p-2 text-operator-muted hover:text-operator-text transition-colors duration-150 disabled:opacity-40 rounded-lg hover:bg-operator-panel"
              title="Voice input"
            >
              <Mic className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => void handleSend()}
              disabled={!input.trim() || composerDisabled}
              className="glow-accent flex items-center justify-center h-10 w-10 ml-0.5 bg-operator-accent text-operator-bg rounded-xl disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
