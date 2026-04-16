import React, { useEffect, useRef, useState, KeyboardEvent } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { MessageBubble } from './MessageBubble';
import { Archive, ArchiveRestore, Paperclip, Mic, Send } from 'lucide-react';

export function ChatWorkspace() {
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const sessions = useAppStore((state) => state.sessions);
  const messagesMap = useAppStore((state) => state.messages);
  const activeRunId = useAppStore((state) => state.activeRunId);
  const appError = useAppStore((state) => state.appError);
  const clearAppError = useAppStore((state) => state.clearAppError);
  const draftSettings = useAppStore((state) => state.draftSettings);
  const draftComposerSeed = useAppStore((state) => state.draftComposerSeed);
  const setDraftComposerSeed = useAppStore((state) => state.setDraftComposerSeed);

  const messages = (activeSessionKey ? messagesMap[activeSessionKey] : undefined) || [];
  const activeSession = sessions.find((session) => session.key === activeSessionKey) || null;
  const isDraft = !activeSession;
  const isArchived = Boolean(activeSession?.archived);
  const composerDisabled = isArchived || Boolean(activeRunId);

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

  return (
    <main className="flex-1 flex flex-col bg-operator-bg relative h-full overflow-hidden">
      {/* Run-in-progress accent bar */}
      {activeRunId && (
        <div className="run-progress-bar h-[2px] w-full bg-operator-accent/10" />
      )}

      {/* Header */}
      <div className="border-b border-operator-border bg-operator-bg flex flex-col">
        <div className="flex items-center justify-between px-5 py-3">
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
                className={`font-semibold text-[17px] text-operator-text font-sans truncate ${activeSession ? 'cursor-pointer hover:text-operator-accent transition-colors duration-150' : ''}`}
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

            {!isDraft && activeSession && (
              <div className="text-[11px] text-operator-muted font-mono mt-0.5 opacity-60 truncate">
                {activeSession.key}
              </div>
            )}

            {/* Metadata badges */}
            <div className="flex flex-wrap items-center gap-1.5 mt-2 text-[10px] font-semibold uppercase tracking-wider">
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
          <div className="flex items-center gap-1.5 shrink-0 ml-3">
            {activeSession && (
              <button
                onClick={() => void wsClient.archiveSession(activeSession.key, !activeSession.archived)}
                className="px-3 py-1.5 border border-operator-border text-operator-muted hover:text-operator-text hover:border-operator-border rounded-lg text-[12px] font-medium flex items-center gap-1.5 transition-all duration-150"
              >
                {activeSession.archived ? <ArchiveRestore className="w-3.5 h-3.5" /> : <Archive className="w-3.5 h-3.5" />}
                {activeSession.archived ? 'Restore' : 'Archive'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Error banner */}
      {appError && (
        <div className="px-5 py-1.5 text-[12px] text-operator-error bg-operator-error/8 border-b border-operator-error/20">
          {appError}
          <button onClick={clearAppError} className="ml-3 underline text-operator-muted hover:text-operator-text transition-colors duration-150">
            dismiss
          </button>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {messages.length === 0 ? (
          <div className="max-w-lg mx-auto mt-10 rounded-2xl border border-operator-border bg-operator-panel/30 p-5 text-center">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-accent mb-2">
              {isDraft ? 'Draft Ready' : isArchived ? 'Archived Session' : 'Session Ready'}
            </div>
            <div className="text-operator-text font-sans text-[14px] mb-1.5">
              {isDraft ? 'Set the runtime in the right panel, then send your first message.' : isArchived ? 'This session is archived. Restore it to continue chatting.' : 'No history loaded for this session yet.'}
            </div>
            <div className="text-operator-muted text-[12px] leading-relaxed">
              {isDraft
                ? 'The first send will create the session and lock provider, model, profile, and mode.'
                : isArchived
                  ? 'Archived sessions stay readable, but input stays disabled until you restore them.'
                  : 'This conversation has not received any assistant output yet.'}
            </div>
          </div>
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
      <div className="px-4 py-3 border-t border-operator-border bg-operator-panel/50">
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

        <div className="flex items-end gap-1.5 bg-operator-bg border border-operator-border rounded-xl p-2 focus-within:border-operator-accent/40 transition-colors duration-150">
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

          <div className="flex items-center gap-0.5 pb-0.5 shrink-0">
            <button
              disabled={composerDisabled}
              className="p-1.5 text-operator-muted hover:text-operator-text transition-colors duration-150 disabled:opacity-40 rounded-lg hover:bg-operator-panel"
              title="Attach file"
            >
              <Paperclip className="w-3.5 h-3.5" />
            </button>
            <button
              disabled={composerDisabled}
              className="p-1.5 text-operator-muted hover:text-operator-text transition-colors duration-150 disabled:opacity-40 rounded-lg hover:bg-operator-panel"
              title="Voice input"
            >
              <Mic className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => void handleSend()}
              disabled={!input.trim() || composerDisabled}
              className="glow-accent flex items-center justify-center h-8 w-8 ml-0.5 bg-operator-accent text-operator-bg rounded-lg disabled:opacity-30 disabled:cursor-not-allowed disabled:shadow-none"
            >
              <Send className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
