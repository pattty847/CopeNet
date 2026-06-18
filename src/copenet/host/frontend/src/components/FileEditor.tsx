// FileEditor — a minimal, reusable plain-text editor (no library, just a styled
// textarea). Edits raw unformatted content (markdown, code, config). Reused
// anywhere we let the operator edit a file in place: workspace viewer, persona
// home, artifact popout. Owns its draft + dirty state; the parent owns saving.

import { useCallback, useEffect, useState } from 'react';
import { Save, X } from 'lucide-react';

export function FileEditor({
  name,
  initialContent,
  onSave,
  onCancel,
  saving = false,
  error = null,
}: {
  name: string;
  initialContent: string;
  onSave: (content: string) => void;
  onCancel: () => void;
  saving?: boolean;
  error?: string | null;
}) {
  const [draft, setDraft] = useState(initialContent);
  // Re-sync when the parent swaps to a different file/content.
  useEffect(() => {
    setDraft(initialContent);
  }, [initialContent]);

  const dirty = draft !== initialContent;

  const handleSave = useCallback(() => {
    if (dirty && !saving) onSave(draft);
  }, [dirty, saving, onSave, draft]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 's') {
      e.preventDefault();
      handleSave();
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="min-w-0 flex-1 truncate font-mono text-[11px] text-shell-text" title={name}>
          {name}
        </span>
        {dirty && <span className="shrink-0 text-[10px] text-amber-400">unsaved</span>}
        <button
          type="button"
          onClick={handleSave}
          disabled={!dirty || saving}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-shell-border bg-shell-accent-soft px-2 py-1 text-[11px] font-medium text-shell-accent transition-colors hover:border-shell-accent/40 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Save className="h-3 w-3" /> {saving ? 'Saving…' : 'Save'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={saving}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-shell-border px-2 py-1 text-[11px] text-shell-muted transition-colors hover:text-shell-text disabled:opacity-50"
        >
          <X className="h-3 w-3" /> Cancel
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/5 px-3 py-2 text-[12px] text-red-400">{error}</div>
      )}

      <textarea
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={handleKeyDown}
        spellCheck={false}
        className="min-h-[300px] w-full resize-y rounded-xl border border-shell-border bg-shell-bg px-4 py-3 font-mono text-[12px] leading-[1.6] text-shell-text outline-none focus:border-shell-accent/40"
      />
      <div className="text-right text-[10px] text-shell-muted/60">⌘/Ctrl+S to save</div>
    </div>
  );
}
