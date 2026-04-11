import React, { useEffect, useRef, useState, KeyboardEvent } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { MessageBubble } from './MessageBubble';
import { Archive, ArchiveRestore, Paperclip, Mic } from 'lucide-react';

export function ChatWorkspace() {
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const sessions = useAppStore((state) => state.sessions);
  const messagesMap = useAppStore((state) => state.messages);
  const activeRunId = useAppStore((state) => state.activeRunId);
  const appError = useAppStore((state) => state.appError);
  const clearAppError = useAppStore((state) => state.clearAppError);

  const messages = (activeSessionKey ? messagesMap[activeSessionKey] : undefined) || [];
  const activeSession = sessions.find((session) => session.key === activeSessionKey) || null;
  const isDraft = !activeSession;

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
      <div className="border-b border-operator-border bg-operator-bg flex flex-col">
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex-1">
            {isEditingTitle ? (
              <input
                autoFocus
                value={editTitleValue}
                onChange={(e) => setEditTitleValue(e.target.value)}
                onBlur={handleTitleSave}
                onKeyDown={(e) => e.key === 'Enter' && handleTitleSave()}
                className="bg-operator-panel border border-operator-accent outline-none font-bold text-xl text-operator-text w-full max-w-md rounded px-2 py-1 -ml-2 font-sans"
              />
            ) : (
              <h1
                className={`font-bold text-xl text-operator-text font-sans ${activeSession ? 'cursor-pointer hover:text-operator-accent transition-colors' : ''}`}
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
              <div className="text-xs text-operator-muted font-mono mt-1 opacity-70">
                {activeSession.key}
              </div>
            )}
          </div>

          <div className="flex items-center gap-2">
            {activeSession?.archived && (
              <span className="px-2 py-1 bg-operator-error/20 text-operator-error text-xs rounded-sm border border-operator-error/30 font-mono mr-2">
                ARCHIVED
              </span>
            )}
            {activeSession && (
              <button
                onClick={() => void wsClient.archiveSession(activeSession.key, !activeSession.archived)}
                className="px-3 py-1.5 border border-operator-border text-operator-muted hover:text-operator-text hover:border-operator-text rounded-sm text-sm font-mono flex items-center gap-2 transition-colors"
              >
                {activeSession.archived ? <ArchiveRestore className="w-4 h-4" /> : <Archive className="w-4 h-4" />}
                {activeSession.archived ? 'Restore' : 'Archive'}
              </button>
            )}
          </div>
        </div>
      </div>

      {appError && (
        <div className="px-6 py-2 text-sm font-mono text-operator-error bg-operator-error/10 border-b border-operator-error/30">
          {appError}
          <button onClick={clearAppError} className="ml-3 underline text-operator-muted hover:text-operator-text">
            dismiss
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto p-6">
        {messages.length === 0 ? (
          <div className="text-operator-muted font-mono text-xs text-center mt-10">
            {isDraft ? 'Configure a draft session and send your first message.' : 'No history loaded for this session yet.'}
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

      <div className="p-4 border-t border-operator-border bg-operator-panel">
        <div className="flex items-end gap-2 bg-operator-bg border border-operator-border rounded-md p-2 focus-within:border-operator-accent transition-colors">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={activeSession?.archived || Boolean(activeRunId)}
            placeholder={activeSession?.archived ? 'SESSION ARCHIVED' : 'Message the agent...'}
            className="flex-1 bg-transparent px-2 py-2 text-sm font-sans text-operator-text focus:outline-none disabled:opacity-50 resize-none max-h-[200px] overflow-y-auto"
            rows={1}
          />
          <div className="flex items-center gap-1 pb-1 shrink-0">
            <button
              disabled={activeSession?.archived || Boolean(activeRunId)}
              className="p-2 text-operator-muted hover:text-operator-text transition-colors disabled:opacity-50 rounded-md hover:bg-operator-panel"
              title="Attach file"
            >
              <Paperclip className="w-4 h-4" />
            </button>
            <button
              disabled={activeSession?.archived || Boolean(activeRunId)}
              className="p-2 text-operator-muted hover:text-operator-text transition-colors disabled:opacity-50 rounded-md hover:bg-operator-panel"
              title="Voice input"
            >
              <Mic className="w-4 h-4" />
            </button>
            <button
              onClick={() => void handleSend()}
              disabled={!input.trim() || activeSession?.archived || Boolean(activeRunId)}
              className="px-4 py-2 ml-1 bg-operator-accent text-operator-bg font-sans font-bold text-sm hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed rounded-md"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}
