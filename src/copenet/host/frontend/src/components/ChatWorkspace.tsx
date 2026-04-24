import React, { useEffect, useRef, useState, KeyboardEvent } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { MessageBubble } from './MessageBubble';
import { WorkingSetCard } from './runtime/WorkingSetCard';
import { Paperclip, Mic, Send } from 'lucide-react';
import { ConversationDebugActions } from './ConversationDebugActions';
import { useIsMobile } from '../lib/responsive';
import { getConversationDebugHelperText } from '../lib/agentMobile';

export function ChatWorkspace() {
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const sessions = useAppStore((state) => state.sessions);
  const messagesMap = useAppStore((state) => state.messages);
  const activeRunId = useAppStore((state) => state.activeRunId);
  const appError = useAppStore((state) => state.appError);
  const clearAppError = useAppStore((state) => state.clearAppError);
  const setAppError = useAppStore((state) => state.setAppError);
  const draftSettings = useAppStore((state) => state.draftSettings);
  const draftComposerSeed = useAppStore((state) => state.draftComposerSeed);
  const setDraftComposerSeed = useAppStore((state) => state.setDraftComposerSeed);

  const messages = (activeSessionKey ? messagesMap[activeSessionKey] : undefined) || [];
  const activeSession = sessions.find((session) => session.key === activeSessionKey) || null;
  const isDraft = !activeSession;
  const isArchived = Boolean(activeSession?.archived);
  const composerDisabled = isArchived || Boolean(activeRunId);
  const canDebugConversation = Boolean(activeSession);
  const isMobile = useIsMobile();
  const activeSessions = sessions.filter((session) => !session.archived).length;
  const archivedSessions = sessions.filter((session) => session.archived).length;
  const connectedProviders = new Set(sessions.filter((session) => !session.archived).map((session) => session.provider).filter(Boolean)).size;

  const [input, setInput] = useState('');
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [editTitleValue, setEditTitleValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (activeSessionKey && messagesMap[activeSessionKey] === undefined) {
      void wsClient.loadHistory(activeSessionKey);
    }
  }, [activeSessionKey, messagesMap]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 200)}px`;
    }
  }, [input]);

  useEffect(() => {
    if (!draftComposerSeed) return;
    setInput((current) => (current.trim() ? current : draftComposerSeed));
    setDraftComposerSeed(null);
  }, [draftComposerSeed, setDraftComposerSeed]);

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

  const applyPromptSeed = (seed: string) => {
    setInput(seed);
    window.requestAnimationFrame(() => textareaRef.current?.focus());
  };

  return (
    <main className="flex-1 flex flex-col bg-operator-bg relative h-full overflow-hidden">
      {/* Run-in-progress accent bar */}
      {activeRunId && (
        <div className="run-progress-bar h-[2px] w-full bg-operator-accent/10" />
      )}

      {/* Header */}
      <div className="border-b border-operator-border bg-operator-bg flex flex-col">
        <div className={`flex gap-3 sm:px-5 sm:py-3 ${isMobile ? 'items-start justify-between px-3 py-2.5' : 'px-4 py-3 items-center justify-between'}`}>
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
                {activeSession?.title || 'New Chat'}
              </h1>
            )}

            {!isDraft && activeSession && !isMobile && (
              <div className="text-[11px] text-operator-muted font-mono mt-0.5 opacity-60 truncate">
                {activeSession.key}
              </div>
            )}

            {/* Metadata badges */}
            <div className={`mt-1.5 flex flex-wrap items-center gap-1.5 font-semibold uppercase tracking-wider ${isMobile ? 'text-[9px]' : 'text-[10px]'}`}>
              <span className={`animate-scale-pop px-2 py-0.5 rounded-md border ${
                isDraft
                  ? 'border-operator-accent/30 bg-operator-accent/8 text-operator-accent'
                  : 'border-operator-success/25 bg-operator-success/8 text-operator-success'
              }`}>
                {isDraft ? 'Draft Session' : 'Locked Session'}
              </span>

              {activeSession?.archived && (
                <span className="px-2 py-0.5 rounded-md border border-operator-error/25 bg-operator-error/8 text-operator-error">
                  Archived
                </span>
              )}

              {isDraft && draftSettings.provider && (
                <span className="px-2 py-0.5 rounded-md border border-operator-border text-operator-muted">
                  {draftSettings.provider}
                </span>
              )}
            </div>
          </div>

          {/* Actions */}
          <div className={`flex shrink-0 items-center gap-1.5 ${isMobile ? 'pt-0' : 'ml-3'}`}>
            <ConversationDebugActions
              disabled={!canDebugConversation}
              helperText={getConversationDebugHelperText(isMobile, isArchived)}
              compact={isMobile}
              onDebugCopy={handleDebugCopy}
              onExportConversation={handleExportConversation}
              onArchiveConversation={activeSession ? () => void wsClient.archiveSession(activeSession.key, !activeSession.archived) : undefined}
            />
          </div>
        </div>
      </div>

      {/* Error banner */}
      {appError && (
        <div className={`${isMobile ? 'px-4' : 'px-5'} py-1.5 text-[12px] text-operator-error bg-operator-error/8 border-b border-operator-error/20`}>
          {appError}
          <button onClick={clearAppError} className="ml-3 underline text-operator-muted hover:text-operator-text transition-colors duration-150">
            dismiss
          </button>
        </div>
      )}

      {/* Working Set — glanceable, pinned above the message stream */}
      <WorkingSetCard sessionKey={activeSessionKey} isDraft={isDraft} />

      {canDebugConversation && !isMobile && (
        <div className="border-b border-operator-border bg-operator-panel/25 px-5 py-2 text-[11px] text-operator-muted">
          <span className="font-semibold text-operator-text">Debug tools</span>
          {' '}
          copy a transcript with session metadata, tool activity, and loaded message content for quick triage or handoff.
        </div>
      )}

      {/* Messages */}
      <div className={`flex-1 overflow-y-auto ${isMobile ? 'px-3 py-2.5' : 'px-5 py-4'}`}>
        {messages.length === 0 ? (
          isDraft ? (
            <div className={`mx-auto w-full max-w-3xl ${isMobile ? 'mt-3' : 'mt-6'} rounded-[28px] border border-operator-accent/15 bg-[linear-gradient(180deg,rgba(251,148,35,0.08),rgba(8,8,9,0.78)_34%,rgba(8,8,9,0.96))] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.28)]`}>
              <div className={`grid gap-4 ${isMobile ? 'grid-cols-1' : 'grid-cols-[minmax(0,1.6fr)_minmax(15rem,1fr)]'}`}>
                <div>
                  <div className="mb-2 inline-flex items-center rounded-full border border-operator-accent/20 bg-operator-accent/8 px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.22em] text-operator-accent">
                    Operator Launchpad
                  </div>
                  <h2 className={`font-serif text-operator-text ${isMobile ? 'text-[24px] leading-8' : 'text-[32px] leading-[1.05]'}`}>
                    Stand up a fresh agent run with a little more intention.
                  </h2>
                  <p className="mt-3 max-w-2xl text-[13px] leading-6 text-operator-muted">
                    Pick a runtime in the inspector, seed the composer with a proven opening move, and let the first send lock the session around a real job instead of a blank box.
                  </p>

                  <div className={`mt-5 grid gap-2.5 ${isMobile ? 'grid-cols-1' : 'grid-cols-3'}`}>
                    {[
                      { label: 'Active sessions', value: String(activeSessions), hint: 'Live operator runs' },
                      { label: 'Archived', value: String(archivedSessions), hint: 'Readable handoffs' },
                      { label: 'Connected runtimes', value: String(connectedProviders || 0), hint: 'Providers in rotation' },
                    ].map((item) => (
                      <div key={item.label} className="rounded-2xl border border-operator-border bg-operator-panel/45 px-3.5 py-3">
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

                  <div className="mt-5">
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
                          className="rounded-full border border-operator-border bg-operator-panel px-3.5 py-2 text-[12px] font-medium text-operator-text transition-colors duration-150 hover:border-operator-accent/35 hover:text-operator-accent"
                        >
                          {option.label}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="rounded-[24px] border border-operator-accent/18 bg-operator-panel/40 p-4">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-operator-accent">
                    Session Doctrine
                  </div>
                  <div className="mt-3 space-y-3 text-[12px] leading-6 text-operator-muted">
                    <p>
                      First send creates and locks the session around its provider, model, profile, and mode.
                    </p>
                    <p>
                      Keep the opener concrete. The cleanest sessions start with a bounded objective, a preferred tool posture, and an explicit output shape.
                    </p>
                    <p className="text-operator-text">
                      Tonight’s setup is ready whenever you are: choose the runtime, seed the ask, and let the console do the rest.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          ) : (
            <div className={`max-w-lg mx-auto ${isMobile ? 'mt-5' : 'mt-10'} rounded-2xl border border-operator-border bg-operator-panel/30 p-5 text-center`}>
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
      <div className={`border-t border-operator-border bg-operator-panel/50 ${isMobile ? 'px-3 pb-3 pt-2.5' : 'px-4 py-3'}`}>
        <div className="flex items-center justify-between px-1 pb-1.5 text-[10px] font-semibold uppercase tracking-wider">
          <span className={`${composerDisabled ? 'text-operator-muted/50' : 'text-operator-muted'}`}>
            {isArchived
              ? 'Composer disabled for archived sessions'
              : activeRunId
                ? 'Assistant response in progress'
                : isDraft
                  ? 'First send creates and locks this session'
                  : 'Session is live and locked to its runtime'}
          </span>
          <span className={isDraft ? 'text-operator-accent' : 'text-operator-success'}>
            {isDraft ? 'Draft' : 'Locked'}
          </span>
        </div>

        <div className={`flex gap-1.5 bg-operator-bg border border-operator-border rounded-xl p-2 focus-within:border-operator-accent/40 transition-colors duration-150 ${isMobile ? 'items-end' : 'items-end'}`}>
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={composerDisabled}
            placeholder={isArchived ? 'SESSION ARCHIVED' : isDraft ? 'Send the first message to create this session...' : 'Message the agent...'}
            className="flex-1 bg-transparent px-2 py-1.5 text-[13px] font-sans text-operator-text focus:outline-none disabled:opacity-40 resize-none max-h-[200px] overflow-y-auto placeholder:text-operator-muted/50"
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
