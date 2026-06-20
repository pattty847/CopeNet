import React, { useEffect, useMemo, useRef, useState, KeyboardEvent } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { MessageBubble } from './MessageBubble';
import { PausedRunBanner } from './PausedRunBanner';
import { ApprovalRequestCard } from './ApprovalRequestCard';
import { Archive, ArrowDown, ArrowUp, Copy, CopyPlus, Download, Ellipsis, GitMerge, Sparkles, X } from 'lucide-react';
import { ConversationDebugActions } from './ConversationDebugActions';
import { PERSONAL_STARTER_PRESETS } from '../lib/personalHistory';
import { useIsMobile } from '../lib/responsive';
import { AgentComposer } from './agents/AgentComposer';
import { buildPersonaCommandHelpText, DRAFT_TRANSCRIPT_SESSION_KEY, parsePersonaSlashCommand, resolvePersonaRuntime } from '../lib/personaCommands';
import { formatConversationMarkdown, formatConversationWithToolActivityMarkdown } from '../lib/chatExport';

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
  const patchDraftSettings = useAppStore((state) => state.patchDraftSettings);
  const mergeDraft = useAppStore((state) => state.mergeDraft);
  const setMergeDraft = useAppStore((state) => state.setMergeDraft);
  const mergeStates = useAppStore((state) => state.mergeStates);
  const setMergeState = useAppStore((state) => state.setMergeState);
  const draftComposerSeed = useAppStore((state) => state.draftComposerSeed);
  const setDraftComposerSeed = useAppStore((state) => state.setDraftComposerSeed);
  const upsertSessionState = useAppStore((state) => state.upsertSessionState);
  const providers = useAppStore((state) => state.providers);
  const profiles = useAppStore((state) => state.profiles);
  const personaSettings = useAppStore((state) => state.personaSettings);
  const runtimeContext = useAppStore((state) => state.runtimeContext);

  const messages = (activeSessionKey ? messagesMap[activeSessionKey] : messagesMap[DRAFT_TRANSCRIPT_SESSION_KEY]) || [];
  const activeSession = sessions.find((session) => session.key === activeSessionKey) || null;
  const activeMergeState = activeSessionKey ? mergeStates[activeSessionKey] || null : null;
  const isDraft = !activeSession;
  const isArchived = Boolean(activeSession?.archived);
  const isMergePrep = Boolean(mergeDraft);
  const composerDisabled = isMergePrep || isArchived || Boolean(activeRunId);
  const canDebugConversation = Boolean(activeSession);
  const isMobile = useIsMobile();
  // On mobile the right-panel approval card lives behind an opt-in sheet, so a
  // paused run never surfaces its prompt. Render it inline here instead.
  const pendingApproval = useAppStore((s) => s.pendingApproval);
  const activeSessions = sessions.filter((session) => !session.archived).length;
  const archivedSessions = sessions.filter((session) => session.archived).length;
  const connectedProviders = new Set(sessions.filter((session) => !session.archived).map((session) => session.provider).filter(Boolean)).size;

  const [input, setInput] = useState('');
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editTitleValue, setEditTitleValue] = useState('');
  const [actionsOpen, setActionsOpen] = useState(false);
  const [copiedAction, setCopiedAction] = useState<'chat' | 'chat_activity' | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const actionsMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (activeSessionKey && messagesMap[activeSessionKey] === undefined) {
      void wsClient.loadHistory(activeSessionKey);
    }
  }, [activeSessionKey, messagesMap]);

  useEffect(() => {
    if (!activeSessionKey) return;
    let cancelled = false;
    void wsClient.resolveMergeState(activeSessionKey).then((mergeState) => {
      if (!cancelled) setMergeState(activeSessionKey, mergeState);
    }).catch(() => {
      if (!cancelled) setMergeState(activeSessionKey, null);
    });
    void wsClient.resolveSessionState(activeSessionKey).then((state) => {
      if (!cancelled && state) upsertSessionState(state);
    }).catch(() => {
      return;
    });
    return () => {
      cancelled = true;
    };
  }, [activeSessionKey, setMergeState, upsertSessionState]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

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

  const appendLocalPersonaReceipt = (content: string) => {
    const sessionKey = activeSession?.key || DRAFT_TRANSCRIPT_SESSION_KEY;
    useAppStore.getState().addMessage(sessionKey, {
      localId: `persona-local-${Date.now()}`,
      sessionKey,
      runId: null,
      role: 'assistant',
      content,
      timestamp: new Date().toISOString(),
      provider: null,
      model: null,
      providerSessionId: null,
      state: 'final',
      toolExecution: null,
      errorMessage: null,
      optimistic: false,
    });
  };

  const formatPersonaSummaryReceipt = (summary: Awaited<ReturnType<typeof wsClient.getPersonaSummary>>) => {
    if (!summary) return '## Persona Home\n\nPersona Home is not active for this runtime yet.';
    return [
      '## Persona Home',
      '',
      `- Persona: \`${summary.personaId}\``,
      `- Privacy: \`${summary.personaPrivacyTier}\``,
      `- Flavor: \`${summary.personaFlavorId || 'none'}\``,
      `- Loaded files: \`${summary.loadedFiles.length}\``,
      `- Root: \`${summary.rootDir}\``,
    ].join('\n');
  };

  const formatPersonaFilesReceipt = (loadedFiles: string[]) => {
    if (!loadedFiles.length) {
      return '## Persona Files\n\nNo persona files are currently loaded for this runtime.';
    }
    return ['## Persona Files', '', ...loadedFiles.map((path) => `- \`${path}\``)].join('\n');
  };

  const handlePersonaCommand = async (rawMessage: string) => {
    const command = parsePersonaSlashCommand(rawMessage);
    if (!command) return false;
    if (command.kind === 'help') {
      appendLocalPersonaReceipt(buildPersonaCommandHelpText());
      return true;
    }

    const runtime = resolvePersonaRuntime(activeSession, draftSettings);
    try {
      if (command.kind === 'summary') {
        const summary = await wsClient.getPersonaSummary({
          provider: runtime.provider,
          model: runtime.model,
          privacyTier: runtime.personaPrivacyTier,
        });
        appendLocalPersonaReceipt(formatPersonaSummaryReceipt(summary));
        return true;
      }

      if (command.kind === 'files') {
        const context = await wsClient.getPersonaContext({
          provider: runtime.provider,
          model: runtime.model,
          privacyTier: runtime.personaPrivacyTier,
        });
        appendLocalPersonaReceipt(formatPersonaFilesReceipt(context?.loadedFiles || []));
        return true;
      }

      if (command.kind === 'privacy') {
        const currentSettings = personaSettings || {
          defaultPersonaId: runtime.personaId || 'default',
          defaultPrivacyTier: runtime.personaPrivacyTier,
          modelOverrides: {},
        };
        await wsClient.updatePersonaSettings({
          ...currentSettings,
          defaultPrivacyTier: command.privacyTier,
        });
        if (!activeSession) {
          patchDraftSettings({ personaPrivacyTier: command.privacyTier });
          appendLocalPersonaReceipt(`## Persona Privacy\n\nDefault privacy is now \`${command.privacyTier}\`, and this draft will use it too.`);
        } else {
          appendLocalPersonaReceipt(
            `## Persona Privacy\n\nDefault privacy is now \`${command.privacyTier}\`. This active session stays \`${runtime.personaPrivacyTier}\` because session identity is locked after first send.`,
          );
        }
        return true;
      }

      if (command.kind === 'onboard') {
        const draft = await wsClient.draftPersonaFlavor({
          provider: runtime.provider,
          model: runtime.model,
        });
        if (!draft) {
          throw new Error('Persona flavor draft returned no content.');
        }
        appendLocalPersonaReceipt(
          `## Persona Onboarding\n\nDrafted a flavor for \`${runtime.provider}\` / \`${runtime.model || 'default'}\` using your private Persona Home baseline. Review the modal before saving.`,
        );
        return true;
      }
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Persona command failed.');
      return true;
    }
    return true;
  };

  const handleSend = async (messageOverride?: string) => {
    const message = (messageOverride ?? input).trim();
    if (!message || activeRunId) return;
    const handledPersonaCommand = await handlePersonaCommand(message);
    if (handledPersonaCommand) {
      setInput('');
      return;
    }
    try {
      await wsClient.sendMessage(message);
      setInput('');
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to send message.');
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

  const handleCopyConversation = async () => {
    if (!activeSession) return;
    try {
      clearAppError();
      const markdown = formatConversationMarkdown({
        session: activeSession,
        messages,
        providerLabel: providerName,
        modelLabel: runtimeSummary.model,
      });
      await navigator.clipboard.writeText(markdown);
      setCopiedAction('chat');
      window.setTimeout(() => setCopiedAction((current) => (current === 'chat' ? null : current)), 1800);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to copy chat.');
    }
  };

  const handleCopyConversationWithToolActivity = async () => {
    if (!activeSession) return;
    try {
      clearAppError();
      const runs = await wsClient.listSessionRuns(activeSession.key, 200);
      const markdown = formatConversationWithToolActivityMarkdown({
        session: activeSession,
        messages,
        runs,
        providerLabel: providerName,
        modelLabel: runtimeSummary.model,
      });
      await navigator.clipboard.writeText(markdown);
      setCopiedAction('chat_activity');
      window.setTimeout(() => setCopiedAction((current) => (current === 'chat_activity' ? null : current)), 1800);
    } catch (error) {
      setAppError(error instanceof Error ? error.message : 'Unable to copy chat with tool activity.');
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

  const providerName = providers.find((provider) => provider.id === (isDraft ? draftSettings.provider : activeSession?.provider))?.displayName
    || (isDraft ? draftSettings.provider : activeSession?.provider)
    || 'None';
  const profileName = profiles.find((profile) => profile.id === (isDraft ? draftSettings.systemPromptId : activeSession?.systemPromptId || ''))?.name
    || (isDraft ? draftSettings.systemPromptId : activeSession?.systemPromptId)
    || 'Default';
  const runtimeSummary = {
    provider: providerName,
    model: (isDraft ? draftSettings.model : activeSession?.model) || 'default',
    profile: profileName,
    statusLabel: isMergePrep ? 'Merge Prep' : isDraft ? 'Draft' : 'Locked',
    workspaceRoot: (isDraft ? draftSettings.workspaceRoot : activeSession?.workspaceRoot) || runtimeContext?.workspaceRoot || '',
    locked: !isDraft && !isMergePrep,
  };
  const handleStartNewSession = () => {
    useAppStore.getState().setActiveSessionKey(null);
    useAppStore.getState().setDraftOpen(false);
    setMergeDraft(null);
    wsClient.beginDraft();
  };

  return (
    <main className="flex-1 flex flex-col bg-operator-bg relative h-full overflow-hidden">
      {/* Run-in-progress accent bar */}
      {activeRunId && (
        <div className="run-progress-bar h-[2px] w-full bg-operator-accent/10" />
      )}

      {/* Paused-run approval banner */}
      <PausedRunBanner />

      {/* Mobile: the approval card lives in the desktop-only right panel, so
          surface it inline here — the run can't proceed until it's answered. */}
      {isMobile && pendingApproval && pendingApproval.status === 'pending' && (
        <div className="border-b border-operator-accent/20 bg-operator-bg px-3 py-2.5">
          <ApprovalRequestCard approval={pendingApproval} />
        </div>
      )}

      {/* Header */}
      <div className="border-b border-operator-border bg-operator-bg">
        <div className={`flex gap-2.5 sm:px-4 sm:py-2 ${isMobile ? 'items-start justify-between px-3 py-2' : 'px-3 py-2 items-center justify-between'}`}>
          <div className="min-w-0 flex flex-1 items-center gap-2.5">
            {/* Status dot */}
            <span
              className={`relative flex h-2 w-2 shrink-0 ${activeSession?.archived ? 'opacity-60' : ''}`}
              title={activeSession?.archived ? 'Archived' : runtimeSummary.statusLabel}
            >
              {!activeSession?.archived && runtimeSummary.locked && (
                <span className="pulse-live absolute inline-flex h-full w-full rounded-full bg-operator-success opacity-50" />
              )}
              <span className={`relative inline-flex h-2 w-2 rounded-full ${activeSession?.archived ? 'bg-operator-error' : runtimeSummary.locked ? 'bg-operator-success' : 'bg-operator-accent'}`} />
            </span>

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
                className="bg-operator-panel border border-operator-accent outline-none font-semibold text-[15.5px] text-operator-text w-full max-w-md rounded-lg px-2 py-0.5 font-sans"
              />
            ) : (
              <h1
                className={`min-w-0 font-semibold ${isMobile ? 'text-[14.5px]' : 'text-[15.5px]'} text-operator-text font-sans truncate tracking-tight ${activeSession ? 'cursor-pointer hover:text-operator-accent transition-colors duration-150' : ''}`}
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

            {!isMobile && (
              <span className="text-[11px] text-operator-muted/85 truncate" title={`${providerName} · ${runtimeSummary.model}`}>
                <span className="text-operator-muted/55">·</span> {providerName}
                <span className="text-operator-muted/40"> / </span>{runtimeSummary.model}
              </span>
            )}
          </div>

          {/* Actions */}
          <div className={`flex shrink-0 items-center ${isMobile ? 'pt-0' : 'ml-3'}`}>
            {isMobile ? (
              <ConversationDebugActions
                disabled={!canDebugConversation}
                compact={true}
                onDebugCopy={handleDebugCopy}
                onCopyConversation={handleCopyConversation}
                onCopyConversationWithToolActivity={handleCopyConversationWithToolActivity}
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
                      onClick={() => { void handleCopyConversation(); setActionsOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-operator-muted hover:text-operator-text hover:bg-operator-panel/60 transition-colors text-left"
                    >
                      <Copy className="w-3.5 h-3.5 shrink-0" />
                      {copiedAction === 'chat' ? 'Copied' : 'Copy Chat'}
                    </button>
                    <button
                      type="button"
                      onClick={() => { void handleCopyConversationWithToolActivity(); setActionsOpen(false); }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-[12px] text-operator-muted hover:text-operator-text hover:bg-operator-panel/60 transition-colors text-left"
                    >
                      <Copy className="w-3.5 h-3.5 shrink-0" />
                      {copiedAction === 'chat_activity' ? 'Copied' : 'Copy Chat + Tool Activity'}
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

      {/* Phase 4 (HARNESS_REBUILD_V2): WorkingSetCard removed. The synthetic
          working-set it rendered is gone (Phase 1) — the transcript is the
          context now. The component file + dead adapter hooks are swept in
          Phase 5. */}

      <div className={`flex-1 overflow-y-auto ${isMobile ? 'px-3 py-3' : 'px-4 py-4'}`}>
        {messages.length === 0 ? (
          mergeDraft ? (
            <div className={`mx-auto w-full max-w-2xl ${isMobile ? 'mt-4' : 'mt-10'}`}>
              <div className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-[0.22em] text-operator-accent/85">
                <GitMerge className="h-3 w-3" />
                Merge workspace
              </div>
              <h2 className={`mt-2 font-serif text-operator-text tracking-tight ${isMobile ? 'text-[24px] leading-[1.15]' : 'text-[30px] leading-[1.08]'}`}>
                One fresh session, drawn from many.
              </h2>
              <p className="mt-2 max-w-xl text-[13px] leading-6 text-operator-muted/90">
                Pick a runtime in the inspector. CopeNet will open the merged session immediately and stream source summaries in.
              </p>

              <div className="mt-5 overflow-hidden rounded-xl border border-operator-border bg-operator-panel/30">
                {mergeSourceSessions.map((session, index) => (
                  <div key={session.key} className="flex items-center gap-2 border-b border-operator-border/55 px-3 py-2 last:border-b-0">
                    <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-operator-border text-[10px] font-mono text-operator-muted/85 tabular-nums">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[12.5px] font-medium text-operator-text">{session.title || session.key}</div>
                      <div className="truncate text-[11px] text-operator-muted/85">
                        {session.provider} · {session.model || 'default'}
                      </div>
                    </div>
                    <div className="flex items-center gap-0.5">
                      <button
                        type="button"
                        onClick={() => moveMergeSource(index, -1)}
                        disabled={index === 0}
                        className="rounded-md p-1 text-operator-muted/70 transition-colors hover:bg-operator-bg/60 hover:text-operator-accent disabled:opacity-30"
                        title="Move up"
                      >
                        <ArrowUp className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => moveMergeSource(index, 1)}
                        disabled={index === mergeSourceSessions.length - 1}
                        className="rounded-md p-1 text-operator-muted/70 transition-colors hover:bg-operator-bg/60 hover:text-operator-accent disabled:opacity-30"
                        title="Move down"
                      >
                        <ArrowDown className="h-3 w-3" />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeMergeSource(session.key)}
                        className="rounded-md p-1 text-operator-muted/70 transition-colors hover:bg-operator-bg/60 hover:text-operator-error"
                        title="Remove source"
                      >
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-3 text-[11px] text-operator-muted/80">
                {mergeSourceSessions.length} source session{mergeSourceSessions.length === 1 ? '' : 's'} · runtime from the inspector
              </div>

              <div className="mt-5 flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => void handleCreateMergedWorkspace()}
                  disabled={mergeSourceSessions.length < 2 || Boolean(activeRunId)}
                  className="glow-accent inline-flex items-center gap-1.5 rounded-xl bg-operator-accent px-3.5 py-2 text-[12px] font-semibold text-operator-bg disabled:cursor-not-allowed disabled:opacity-40"
                >
                  <GitMerge className="h-3.5 w-3.5" />
                  Create merged workspace
                </button>
                <button
                  type="button"
                  onClick={() => setMergeDraft(null)}
                  className="inline-flex items-center gap-1.5 rounded-xl border border-operator-border px-3 py-2 text-[12px] font-medium text-operator-muted transition-colors hover:border-operator-accent/30 hover:text-operator-text"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : isDraft ? (
            <div className={`mx-auto w-full max-w-2xl ${isMobile ? 'mt-4' : 'mt-10'}`}>
              <div className="text-[10px] font-semibold uppercase tracking-[0.22em] text-operator-accent/85">
                New Session
              </div>
              <h2 className={`mt-2 font-serif text-operator-text ${isMobile ? 'text-[26px] leading-[1.15]' : 'text-[32px] leading-[1.08]'} tracking-tight`}>
                What are we working on?
              </h2>
              <p className="mt-2 text-[13px] leading-6 text-operator-muted/90">
                Pick a runtime in the inspector and the first message will lock this session around the job.
              </p>

              <div className="mt-6 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.16em] text-operator-muted/75">
                <span>Opening moves</span>
                <span className="tabular-nums text-operator-muted/50">
                  {activeSessions} active · {archivedSessions} archived
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
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
                    className="rounded-full border border-operator-border bg-operator-panel/60 px-3 py-1.5 text-[12px] font-medium text-operator-text transition-all duration-150 hover:border-operator-accent/35 hover:text-operator-accent hover:bg-operator-panel"
                  >
                    {option.label}
                  </button>
                ))}
              </div>

              <div className="mt-6 grid gap-2 sm:grid-cols-3">
                {PERSONAL_STARTER_PRESETS.map((option) => {
                  const active = draftStarterIntent?.id === option.id;
                  return (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => handleStarterIntent(option.id, option.seed)}
                      className={`rounded-xl border px-3 py-2.5 text-left transition-all duration-150 ${
                        active
                          ? 'border-operator-accent/40 bg-operator-accent/8 shadow-[inset_0_0_0_1px_var(--color-operator-accent)]/[.06]'
                          : 'border-operator-border bg-operator-panel/30 hover:border-operator-accent/28 hover:bg-operator-panel/55'
                      }`}
                    >
                      <div className="text-[12px] font-semibold text-operator-text">{option.label}</div>
                      <div className="mt-1 text-[11px] leading-5 text-operator-muted/85">{option.cue}</div>
                    </button>
                  );
                })}
              </div>
            </div>
          ) : (
            <div className={`max-w-md mx-auto ${isMobile ? 'mt-6' : 'mt-12'} text-center`}>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-operator-accent/85">
                {isArchived ? 'Archived' : 'Ready'}
              </div>
              <div className="mt-2 font-serif text-operator-text text-[22px] leading-tight">
                {isArchived ? 'This session is read-only.' : 'Send a message to begin.'}
              </div>
              <div className="mt-2 text-[12px] leading-relaxed text-operator-muted/85">
                {isArchived
                  ? 'Restore from the actions menu to continue the conversation.'
                  : 'No assistant output yet — your first message will kick things off.'}
              </div>
            </div>
          )
        ) : (
          <div className="mx-auto flex w-full max-w-3xl flex-col">
            {messages.map((message) => (
              <MessageBubble key={message.localId} message={message} />
            ))}
            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Composer */}
      <AgentComposer
        value={input}
        onChange={setInput}
        onKeyDown={handleKeyDown}
        onSend={(messageOverride) => void handleSend(messageOverride)}
        optimizationProviderId={isDraft ? draftSettings.provider : activeSession?.provider || draftSettings.provider}
        optimizationModelId={isDraft ? draftSettings.model : activeSession?.model || draftSettings.model}
        disabled={composerDisabled}
        placeholder={isMergePrep ? 'Create the merged workspace to begin...' : isArchived ? 'SESSION ARCHIVED' : isDraft ? 'Send the first message to create this session...' : 'Message the agent...'}
        statusCopy={
          isMergePrep
            ? 'Create the merged workspace before sending messages'
            : isArchived
              ? 'Composer disabled for archived sessions'
              : activeRunId
                ? 'Assistant response in progress'
                : isDraft
                  ? 'First send creates and locks this session'
                  : 'Session is live and locked to its runtime'
        }
        runtimeSummary={runtimeSummary}
        onStartNewSession={handleStartNewSession}
      />
    </main>
  );
}
