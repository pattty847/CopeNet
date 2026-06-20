import { useEffect, useState } from 'react';
import { AlertCircle, LoaderCircle, Plus, ShieldCheck, Trash2 } from 'lucide-react';
import { wsClient } from '../lib/wsClient';
import type { ShellAllowlistEntry } from '../types/backend';

/**
 * Manage the global shell allowlist (Access & Permissions — Brick F). These are the
 * commands the operator has "Always allow"-ed: they run with full shell in any Access
 * mode without asking again. Editable here, or grown one prompt at a time from the
 * approval card's "Always allow" button.
 */
export function PermissionsSettingsPanel() {
  const [commands, setCommands] = useState<ShellAllowlistEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [newCommand, setNewCommand] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const list = await wsClient.listShellAllowlist();
        if (!cancelled) setCommands(list);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : 'Failed to load allowlist');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const addCommand = async () => {
    const command = newCommand.trim();
    if (!command || busy) return;
    setBusy(true);
    setError(null);
    try {
      setCommands(await wsClient.addShellAllowlist(command));
      setNewCommand('');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add command');
    } finally {
      setBusy(false);
    }
  };

  const removeCommand = async (command: string) => {
    setError(null);
    try {
      setCommands(await wsClient.removeShellAllowlist(command));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to remove command');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-shell-text">
        <ShieldCheck className="h-4 w-4 text-shell-accent" />
        <h2 className="text-[15px] font-semibold">Global shell allowlist</h2>
      </div>
      <p className="text-[13px] leading-5 text-shell-muted">
        Commands here run automatically in any Access mode — no prompt. CopeNet adds to this
        list when you pick <span className="font-medium text-shell-text">Always allow</span> on
        an approval. Stored exactly as approved; remove anything you no longer trust.
      </p>

      {error && (
        <div className="flex items-center gap-2 rounded-xl border border-shell-error/25 bg-shell-error/8 px-3 py-2 text-[13px] text-shell-error">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </div>
      )}

      <div className="flex gap-2">
        <input
          type="text"
          value={newCommand}
          onChange={(e) => setNewCommand(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') void addCommand(); }}
          placeholder="e.g. npm test"
          spellCheck={false}
          className="flex-1 rounded-xl border border-shell-border bg-shell-bg px-3 py-2 font-mono text-[13px] text-shell-text outline-none transition-colors duration-150 focus:border-shell-border-strong"
        />
        <button
          type="button"
          onClick={() => void addCommand()}
          disabled={busy || !newCommand.trim()}
          className="inline-flex items-center gap-1.5 rounded-xl border border-shell-accent/30 bg-shell-accent/10 px-3.5 py-2 text-[13px] font-semibold text-shell-accent transition-colors duration-150 hover:bg-shell-accent/20 disabled:opacity-40"
        >
          {busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Add
        </button>
      </div>

      <div className="space-y-1.5">
        <div className="text-[10px] font-semibold uppercase tracking-[0.2em] text-shell-muted">
          Allowed commands ({commands.length})
        </div>
        {loading ? (
          <div className="flex items-center gap-2 px-1 py-3 text-[13px] text-shell-muted">
            <LoaderCircle className="h-4 w-4 animate-spin" /> Loading…
          </div>
        ) : commands.length === 0 ? (
          <div className="rounded-xl border border-dashed border-shell-border bg-shell-bg/50 px-3 py-4 text-center text-[13px] text-shell-muted">
            Nothing always-allowed yet. Approve a command with “Always allow” to add it here.
          </div>
        ) : (
          <ul className="space-y-1">
            {commands.map((entry) => (
              <li
                key={entry.command}
                className="group flex items-center justify-between gap-3 rounded-xl border border-shell-border bg-shell-bg px-3 py-2"
              >
                <code className="min-w-0 flex-1 truncate font-mono text-[13px] text-shell-text" title={entry.command}>
                  {entry.command}
                </code>
                <button
                  type="button"
                  onClick={() => void removeCommand(entry.command)}
                  title="Remove from allowlist"
                  className="shrink-0 rounded-lg p-1.5 text-shell-muted transition-colors duration-150 hover:bg-shell-error/10 hover:text-shell-error"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
