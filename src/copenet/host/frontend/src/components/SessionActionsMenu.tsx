import type React from 'react';
import { Archive, Copy, CopyPlus, Download, Sparkles } from 'lucide-react';

type CopiedAction = 'chat' | 'chat_activity' | null;

interface SessionActionsMenuProps {
  copiedAction: CopiedAction;
  archived: boolean;
  canArchive: boolean;
  onDebugCopy: () => void;
  onCopyConversation: () => void;
  onCopyConversationWithToolActivity: () => void;
  onExportConversation: () => void;
  onCreatePulse: () => void;
  onArchiveConversation: () => void;
}

const actionClass = {
  inspect: 'border-sky-400/25 bg-sky-400/8 text-sky-500 group-hover/menuitem:border-sky-400/45 group-hover/menuitem:bg-sky-400/14',
  copy: 'border-emerald-400/25 bg-emerald-400/8 text-emerald-600 group-hover/menuitem:border-emerald-400/45 group-hover/menuitem:bg-emerald-400/14',
  pulse: 'border-operator-accent/25 bg-operator-accent/10 text-operator-accent group-hover/menuitem:border-operator-accent/45 group-hover/menuitem:bg-operator-accent/16',
  manage: 'border-rose-400/25 bg-rose-400/8 text-rose-500 group-hover/menuitem:border-rose-400/45 group-hover/menuitem:bg-rose-400/14',
};

function MenuItem({
  label,
  tone,
  icon,
  onClick,
}: {
  label: string;
  tone: keyof typeof actionClass;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group/menuitem flex w-full items-center gap-2.5 px-3 py-2 text-left text-[12px] text-operator-muted transition-colors hover:bg-operator-bg/65 hover:text-operator-text"
    >
      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-lg border transition-colors ${actionClass[tone]}`}>
        {icon}
      </span>
      <span className="min-w-0 flex-1 truncate">{label}</span>
    </button>
  );
}

function MenuDivider() {
  return <div className="my-1 border-t border-operator-border/60" />;
}

export function SessionActionsMenu({
  copiedAction,
  archived,
  canArchive,
  onDebugCopy,
  onCopyConversation,
  onCopyConversationWithToolActivity,
  onExportConversation,
  onCreatePulse,
  onArchiveConversation,
}: SessionActionsMenuProps) {
  return (
    <div className="absolute right-0 top-full z-20 mt-1.5 w-56 overflow-hidden rounded-xl border border-operator-border bg-operator-panel py-1 shadow-lg">
      <MenuItem
        label="Debug Copy"
        tone="inspect"
        icon={<CopyPlus className="h-3.5 w-3.5" />}
        onClick={onDebugCopy}
      />
      <MenuDivider />
      <MenuItem
        label={copiedAction === 'chat' ? 'Copied' : 'Copy Chat'}
        tone="copy"
        icon={<Copy className="h-3.5 w-3.5" />}
        onClick={onCopyConversation}
      />
      <MenuItem
        label={copiedAction === 'chat_activity' ? 'Copied' : 'Copy Chat + Tool Activity'}
        tone="copy"
        icon={<Copy className="h-3.5 w-3.5" />}
        onClick={onCopyConversationWithToolActivity}
      />
      <MenuItem
        label="Export"
        tone="copy"
        icon={<Download className="h-3.5 w-3.5" />}
        onClick={onExportConversation}
      />
      <MenuDivider />
      <MenuItem
        label="Create Pulse"
        tone="pulse"
        icon={<Sparkles className="h-3.5 w-3.5" />}
        onClick={onCreatePulse}
      />
      {canArchive ? (
        <>
          <MenuDivider />
          <MenuItem
            label={archived ? 'Restore' : 'Archive'}
            tone="manage"
            icon={<Archive className="h-3.5 w-3.5" />}
            onClick={onArchiveConversation}
          />
        </>
      ) : null}
    </div>
  );
}
