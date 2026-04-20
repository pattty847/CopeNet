import React, { useState } from 'react';
import { CopyPlus, Download, Check, Archive } from 'lucide-react';
import { getDebugActionLabel } from '../lib/agentMobile';

type Props = {
  disabled?: boolean;
  helperText?: string;
  compact?: boolean;
  onDebugCopy: () => Promise<void>;
  onExportConversation: () => Promise<void>;
  onArchiveConversation?: () => void;
};

export function ConversationDebugActions({
  disabled = false,
  helperText,
  onDebugCopy,
  onExportConversation,
  compact = false,
  onArchiveConversation,
}: Props) {
  const [busyAction, setBusyAction] = useState<'copy' | 'export' | null>(null);
  const [copied, setCopied] = useState(false);

  const handleDebugCopy = async () => {
    if (disabled || busyAction) return;
    setBusyAction('copy');
    try {
      await onDebugCopy();
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
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

  return (
    <div className={`flex items-center gap-1.5 ${compact ? 'w-full flex-nowrap' : ''}`}>
      <button
        onClick={() => void handleDebugCopy()}
        disabled={disabled || busyAction !== null}
        className={`${compact ? 'px-2 py-1.5 text-[11px] min-w-0 flex-1 justify-center' : 'px-3 py-1.5 text-[12px]'} border border-operator-border text-operator-muted hover:text-operator-accent hover:border-operator-accent/30 rounded-lg font-medium flex items-center gap-1.5 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed`}
        title="Create a fresh debug copy of this conversation"
      >
        {copied ? <Check className="w-3.5 h-3.5" /> : <CopyPlus className="w-3.5 h-3.5" />}
        <span className="truncate">{busyAction === 'copy' ? 'Copying…' : copied ? 'Copied' : getDebugActionLabel('copy', compact)}</span>
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
