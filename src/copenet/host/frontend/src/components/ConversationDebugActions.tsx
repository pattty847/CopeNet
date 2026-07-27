import React, { useState } from 'react';
import { Copy, CopyPlus, Download, Check, Archive, Ellipsis, Sparkles } from 'lucide-react';
import { getConversationActionTriggerLabel, getDebugActionLabel } from '../lib/agentMobile';
import { MobileSheet } from './mobile/MobileSheet';

type Props = {
  disabled?: boolean;
  helperText?: string;
  compact?: boolean;
  onDebugCopy: () => Promise<void>;
  onCopyConversation: () => Promise<boolean>;
  onCopyConversationWithToolActivity: () => Promise<boolean>;
  onExportConversation: () => Promise<void>;
  onArchiveConversation?: () => void;
  onCreatePulse?: () => Promise<void>;
};

export function ConversationDebugActions({
  disabled = false,
  helperText,
  onDebugCopy,
  onCopyConversation,
  onCopyConversationWithToolActivity,
  onExportConversation,
  compact = false,
  onArchiveConversation,
  onCreatePulse,
}: Props) {
  const [busyAction, setBusyAction] = useState<'copy' | 'chat_copy' | 'chat_activity_copy' | 'export' | 'pulse' | null>(null);
  const [copiedAction, setCopiedAction] = useState<'debug' | 'chat' | 'chat_activity' | null>(null);
  const [mobileActionsOpen, setMobileActionsOpen] = useState(false);

  const handleDebugCopy = async () => {
    if (disabled || busyAction) return;
    setBusyAction('copy');
    try {
      await onDebugCopy();
      setCopiedAction('debug');
      window.setTimeout(() => setCopiedAction((current) => (current === 'debug' ? null : current)), 1800);
    } finally {
      setBusyAction(null);
    }
  };

  const handleCopyConversation = async () => {
    if (disabled || busyAction) return;
    setBusyAction('chat_copy');
    try {
      if (await onCopyConversation()) {
        setCopiedAction('chat');
        window.setTimeout(() => setCopiedAction((current) => (current === 'chat' ? null : current)), 1800);
      }
    } finally {
      setBusyAction(null);
    }
  };

  const handleCopyConversationWithToolActivity = async () => {
    if (disabled || busyAction) return;
    setBusyAction('chat_activity_copy');
    try {
      if (await onCopyConversationWithToolActivity()) {
        setCopiedAction('chat_activity');
        window.setTimeout(() => setCopiedAction((current) => (current === 'chat_activity' ? null : current)), 1800);
      }
    } finally {
      setBusyAction(null);
    }
  };

  const handleCreatePulse = async () => {
    if (disabled || busyAction) return;
    setBusyAction('pulse');
    try {
      await onCreatePulse?.();
    } finally {
      setBusyAction(null);
    }
  };

  const handleExport = async () => {
    if (disabled || busyAction) return;
    setBusyAction('export');
    try {
      await onExportConversation();
    } finally {
      setBusyAction(null);
    }
  };

  if (compact) {
    return (
      <>
        <div className="flex items-center">
          <button
            type="button"
            onClick={() => setMobileActionsOpen(true)}
            disabled={disabled}
            className="inline-flex items-center gap-2 rounded-xl border border-operator-border px-3 py-2 text-[12px] font-medium text-operator-muted transition-all duration-150 hover:border-operator-accent/30 hover:text-operator-text disabled:cursor-not-allowed disabled:opacity-40"
            title="Conversation actions"
          >
            <Ellipsis className="h-4 w-4" />
            <span>{getConversationActionTriggerLabel(true)}</span>
          </button>
        </div>

        <MobileSheet
          open={mobileActionsOpen}
          onClose={() => setMobileActionsOpen(false)}
          title="Conversation Actions"
        >
          <div className="space-y-2 px-3 py-3">
            <button
              type="button"
              onClick={() => {
                void handleDebugCopy();
                setMobileActionsOpen(false);
              }}
              disabled={disabled || busyAction !== null}
              className="flex w-full items-center gap-3 rounded-2xl border border-operator-border bg-operator-panel px-4 py-3 text-left text-[14px] font-medium text-operator-text disabled:opacity-40"
            >
              {copiedAction === 'debug' ? <Check className="h-4 w-4 shrink-0" /> : <CopyPlus className="h-4 w-4 shrink-0" />}
              <span>{busyAction === 'copy' ? 'Creating…' : 'Create Debug Session'}</span>
            </button>
            <button
              type="button"
              onClick={() => {
                void handleCopyConversation();
                setMobileActionsOpen(false);
              }}
              disabled={disabled || busyAction !== null}
              className="flex w-full items-center gap-3 rounded-2xl border border-operator-border bg-operator-panel px-4 py-3 text-left text-[14px] font-medium text-operator-text disabled:opacity-40"
            >
              {copiedAction === 'chat' ? <Check className="h-4 w-4 shrink-0" /> : <Copy className="h-4 w-4 shrink-0" />}
              <span>{busyAction === 'chat_copy' ? 'Copying…' : copiedAction === 'chat' ? 'Copied' : 'Copy Chat (Messages Only)'}</span>
            </button>
            <button
              type="button"
              onClick={() => {
                void handleCopyConversationWithToolActivity();
                setMobileActionsOpen(false);
              }}
              disabled={disabled || busyAction !== null}
              className="flex w-full items-center gap-3 rounded-2xl border border-operator-border bg-operator-panel px-4 py-3 text-left text-[14px] font-medium text-operator-text disabled:opacity-40"
            >
              {copiedAction === 'chat_activity' ? <Check className="h-4 w-4 shrink-0" /> : <Copy className="h-4 w-4 shrink-0" />}
              <span>{busyAction === 'chat_activity_copy' ? 'Copying…' : copiedAction === 'chat_activity' ? 'Copied' : 'Copy Chat + Tools'}</span>
            </button>
            <button
              type="button"
              onClick={() => {
                void handleExport();
                setMobileActionsOpen(false);
              }}
              disabled={disabled || busyAction !== null}
              className="flex w-full items-center gap-3 rounded-2xl border border-operator-border bg-operator-panel px-4 py-3 text-left text-[14px] font-medium text-operator-text disabled:opacity-40"
            >
              <Download className="h-4 w-4 shrink-0" />
              <span>{busyAction === 'export' ? 'Exporting…' : 'Export Chat + Tools'}</span>
            </button>
            {onCreatePulse ? (
              <button
                type="button"
                onClick={() => {
                  void handleCreatePulse();
                  setMobileActionsOpen(false);
                }}
                disabled={disabled || busyAction !== null}
                className="flex w-full items-center gap-3 rounded-2xl border border-operator-border bg-operator-panel px-4 py-3 text-left text-[14px] font-medium text-operator-text disabled:opacity-40"
              >
                <Sparkles className="h-4 w-4 shrink-0" />
                <span>{busyAction === 'pulse' ? 'Creating…' : 'Create Pulse'}</span>
              </button>
            ) : null}
            {onArchiveConversation ? (
              <button
                type="button"
                onClick={() => {
                  onArchiveConversation();
                  setMobileActionsOpen(false);
                }}
                disabled={disabled || busyAction !== null}
                className="flex w-full items-center gap-3 rounded-2xl border border-operator-border bg-operator-panel px-4 py-3 text-left text-[14px] font-medium text-operator-text disabled:opacity-40"
              >
                <Archive className="h-4 w-4 shrink-0" />
                <span>{getDebugActionLabel('archive', true)}</span>
              </button>
            ) : null}
          </div>
        </MobileSheet>
      </>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <button
        onClick={() => void handleDebugCopy()}
        disabled={disabled || busyAction !== null}
        className={`${compact ? 'px-2 py-1.5 text-[11px] min-w-0 flex-1 justify-center' : 'px-3 py-1.5 text-[12px]'} border border-operator-border text-operator-muted hover:text-operator-accent hover:border-operator-accent/30 rounded-lg font-medium flex items-center gap-1.5 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed`}
        title="Create a fresh debug copy of this conversation"
      >
        {copiedAction === 'debug' ? <Check className="w-3.5 h-3.5" /> : <CopyPlus className="w-3.5 h-3.5" />}
        <span className="truncate">{busyAction === 'copy' ? 'Copying…' : copiedAction === 'debug' ? 'Copied' : getDebugActionLabel('copy', compact)}</span>
      </button>
      <button
        onClick={() => void handleCopyConversation()}
        disabled={disabled || busyAction !== null}
        className={`${compact ? 'px-2 py-1.5 text-[11px] min-w-0 flex-1 justify-center' : 'px-3 py-1.5 text-[12px]'} border border-operator-border text-operator-muted hover:text-operator-text hover:border-operator-border rounded-lg font-medium flex items-center gap-1.5 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed`}
        title="Copy this chat as markdown"
      >
        {copiedAction === 'chat' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
        <span className="truncate">{busyAction === 'chat_copy' ? 'Copying…' : copiedAction === 'chat' ? 'Copied' : 'Copy Chat'}</span>
      </button>
      <button
        onClick={() => void handleCopyConversationWithToolActivity()}
        disabled={disabled || busyAction !== null}
        className={`${compact ? 'px-2 py-1.5 text-[11px] min-w-0 flex-1 justify-center' : 'px-3 py-1.5 text-[12px]'} border border-operator-border text-operator-muted hover:text-operator-text hover:border-operator-border rounded-lg font-medium flex items-center gap-1.5 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed`}
        title="Copy this chat and tool activity as markdown"
      >
        {copiedAction === 'chat_activity' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
        <span className="truncate">{busyAction === 'chat_activity_copy' ? 'Copying…' : copiedAction === 'chat_activity' ? 'Copied' : 'Copy Chat + Tools'}</span>
      </button>
      <button
        onClick={() => void handleExport()}
        disabled={disabled || busyAction !== null}
        className={`${compact ? 'px-2 py-1.5 text-[11px] min-w-0 flex-1 justify-center' : 'px-3 py-1.5 text-[12px]'} border border-operator-border text-operator-muted hover:text-operator-text hover:border-operator-border rounded-lg font-medium flex items-center gap-1.5 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed`}
        title="Export this conversation"
      >
        <Download className="w-3.5 h-3.5" />
        <span className="truncate">{busyAction === 'export' ? 'Exporting…' : getDebugActionLabel('export', compact)}</span>
      </button>
      {onCreatePulse ? (
        <button
          onClick={() => void handleCreatePulse()}
          disabled={disabled || busyAction !== null}
          className={`${compact ? 'px-2 py-1.5 text-[11px] min-w-0 flex-1 justify-center' : 'px-3 py-1.5 text-[12px]'} border border-operator-border text-operator-muted hover:text-operator-accent hover:border-operator-accent/30 rounded-lg font-medium flex items-center gap-1.5 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed`}
          title="Create a Pulse from this conversation"
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span className="truncate">{busyAction === 'pulse' ? 'Creating…' : 'Create Pulse'}</span>
        </button>
      ) : null}
      {onArchiveConversation ? (
        <button
          onClick={onArchiveConversation}
          disabled={disabled || busyAction !== null}
          className={`${compact ? 'px-2 py-1.5 text-[11px] min-w-0 flex-1 justify-center' : 'px-3 py-1.5 text-[12px]'} border border-operator-border text-operator-muted hover:text-operator-text hover:border-operator-border rounded-lg font-medium flex items-center gap-1.5 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed`}
          title="Archive this conversation"
        >
          <Archive className="w-3.5 h-3.5 shrink-0" />
          <span className="truncate">{getDebugActionLabel('archive', compact)}</span>
        </button>
      ) : null}
      {helperText ? <span className="ml-1 text-[10px] text-operator-muted">{helperText}</span> : null}
    </div>
  );
}
