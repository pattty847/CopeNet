// WorkspaceFileViewer — open a file from the active session's workspace and see
// it rendered (markdown formatted, code highlighted) instead of raw text. Lives
// in Data & Tools. Read-only; backed by the workspace.listFiles / readFile RPCs.

import { useCallback, useEffect, useState } from 'react';
import { FileText, Mail, RefreshCw, Folder } from 'lucide-react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { ChatMarkdown } from './ChatMarkdown';
import { HighlightedCode } from './runtime/CodeViews';
import type { WorkspaceFile, WorkspaceFileContent } from '../types/backend';

function iconFor(file: WorkspaceFile) {
  if (file.path.startsWith('inbox/')) return Mail;
  return FileText;
}

function FileBody({ doc }: { doc: WorkspaceFileContent }) {
  if (doc.kind === 'markdown') {
    return (
      <div className="rounded-xl border border-shell-border bg-shell-bg px-5 py-4">
        <ChatMarkdown content={doc.content} />
      </div>
    );
  }
  if (doc.kind === 'code') {
    return (
      <div className="overflow-x-auto rounded-xl border border-shell-border bg-shell-bg p-3 text-[12px] font-mono leading-[1.6]">
        {doc.content.split('\n').map((line, i) => (
          <div key={i} className="whitespace-pre">
            <HighlightedCode text={line} lang={doc.ext || 'txt'} />
          </div>
        ))}
      </div>
    );
  }
  return (
    <pre className="overflow-x-auto whitespace-pre-wrap break-words rounded-xl border border-shell-border bg-shell-bg px-4 py-3 text-[12px] font-mono text-shell-text">
      {doc.content}
    </pre>
  );
}

export function WorkspaceFileViewer() {
  const activeSessionKey = useAppStore((s) => s.activeSessionKey);
  const [root, setRoot] = useState<string>('');
  const [files, setFiles] = useState<WorkspaceFile[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [doc, setDoc] = useState<WorkspaceFileContent | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!activeSessionKey) return;
    setLoading(true);
    setError(null);
    try {
      const res = await wsClient.listWorkspaceFiles(activeSessionKey);
      setRoot(res.root);
      setFiles(res.files);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [activeSessionKey]);

  useEffect(() => {
    setSelected(null);
    setDoc(null);
    refresh();
  }, [refresh]);

  const openFile = useCallback(
    async (path: string) => {
      if (!activeSessionKey) return;
      setSelected(path);
      setDoc(null);
      setError(null);
      try {
        setDoc(await wsClient.readWorkspaceFile(activeSessionKey, path));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [activeSessionKey],
  );

  if (!activeSessionKey) {
    return (
      <div className="rounded-[20px] border border-dashed border-shell-border bg-shell-panel px-6 py-10 text-center text-sm text-shell-muted">
        Open a session in <span className="font-semibold text-shell-text">Agents</span> first — the viewer reads that
        session's workspace.
      </div>
    );
  }

  return (
    <section className="rounded-[20px] border border-shell-border bg-shell-panel p-4">
      <header className="mb-3 flex items-center gap-2">
        <Folder className="h-4 w-4 text-shell-accent" />
        <h3 className="text-sm font-semibold text-shell-text">Workspace Files</h3>
        <code className="ml-1 truncate text-[10px] text-shell-muted" title={root}>{root}</code>
        <button
          type="button"
          onClick={refresh}
          className="ml-auto inline-flex items-center gap-1 rounded-lg border border-shell-border px-2 py-1 text-[11px] text-shell-muted transition-colors hover:text-shell-accent"
        >
          <RefreshCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </header>

      <div className="grid gap-3 md:grid-cols-[minmax(180px,260px)_minmax(0,1fr)]">
        <div className="rounded-xl border border-shell-border bg-shell-bg p-1.5">
          {files.length === 0 && !loading && (
            <div className="px-2 py-4 text-center text-[12px] text-shell-muted">No viewable files.</div>
          )}
          <ul className="space-y-0.5">
            {files.map((file) => {
              const Icon = iconFor(file);
              const isSel = file.path === selected;
              return (
                <li key={file.path}>
                  <button
                    type="button"
                    onClick={() => openFile(file.path)}
                    className={`flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[12px] transition-colors ${
                      isSel ? 'bg-shell-accent-soft text-shell-accent' : 'text-shell-text hover:bg-shell-border/30'
                    }`}
                  >
                    <Icon className="h-3.5 w-3.5 shrink-0 opacity-70" />
                    <span className="truncate">{file.path}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>

        <div className="min-h-[220px]">
          {error && <div className="rounded-lg border border-red-500/40 bg-red-500/5 px-3 py-2 text-[12px] text-red-400">{error}</div>}
          {!selected && !error && (
            <div className="flex h-full items-center justify-center rounded-xl border border-dashed border-shell-border text-[12px] text-shell-muted">
              Select a file to view it rendered.
            </div>
          )}
          {selected && !doc && !error && (
            <div className="flex h-full items-center justify-center text-[12px] text-shell-muted">Loading…</div>
          )}
          {doc && (
            <div>
              <div className="mb-2 flex items-center gap-2 text-[11px] text-shell-muted">
                <span className="font-mono text-shell-text">{doc.name}</span>
                <span>· {doc.kind}</span>
                {doc.truncated && <span className="text-amber-400">· truncated</span>}
              </div>
              <FileBody doc={doc} />
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
