import React, { useState } from 'react';
import { CopyPlus, Download, Check } from 'lucide-react';

type Props = {
  disabled?: boolean;
  helperText?: string;
  onDebugCopy: () => Promise<void>;
  onExportConversation: () => Promise<void>;
};

export function ConversationDebugActions({
  disabled = false,
  helperText,
  onDebugCopy,
  onExportConversation,
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
    <div className="flex items-center gap-1.5">
      <button
        onClick={() => void handleDebugCopy()}
        disabled={disabled || busyAction !== null}
        className="px-3 py-1.5 border border-operator-border text-operator-muted hover:text-operator-accent hover:border-operator-accent/30 rounded-lg text-[12px] font-medium flex items-center gap-1.5 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
        title="Create a fresh debug copy of this conversation"
      >
        {copied ? <Check className="w-3.5 h-3.5" /> : <CopyPlus className="w-3.5 h-3.5" />}
        {busyAction === 'copy' ? 'Copying…' : copied ? 'Copied' : 'Debug Copy'}
      </button>
      <button
        onClick={() => void handleExport()}
        disabled={disabled || busyAction !== null}
        className="px-3 py-1.5 border border-operator-border text-operator-muted hover:text-operator-text hover:border-operator-border rounded-lg text-[12px] font-medium flex items-center gap-1.5 transition-all duration-150 disabled:opacity-40 disabled:cursor-not-allowed"
        title="Export this conversation"
      >
        <Download className="w-3.5 h-3.5" />
        {busyAction === 'export' ? 'Exporting…' : 'Export'}
      </button>
      {helperText ? <span className="ml-1 text-[10px] text-operator-muted">{helperText}</span> : null}
    </div>
  );
}
