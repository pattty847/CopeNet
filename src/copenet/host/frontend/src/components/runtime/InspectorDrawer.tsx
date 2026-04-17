import { useEffect, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { X, FileText, Package, MessageSquareQuote, FileDiff, Layers, CheckCircle2, XCircle, Terminal } from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { getArtifactById, getBatchById } from '../../runtime/mocks';
import type { Artifact } from '../../runtime/types';
import { DiffArtifactView } from './DiffArtifactView';

function ArtifactBody({ artifact }: { artifact: Artifact }) {
  if (artifact.kind === 'patch_plan' || artifact.kind === 'diff') {
    return <DiffArtifactView artifact={artifact} />;
  }

  const Icon =
    artifact.kind === 'summary'
      ? FileText
      : artifact.kind === 'answer'
      ? MessageSquareQuote
      : Package;

  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-operator-border bg-operator-panel/40 px-3 py-2.5">
        <div className="flex items-center gap-2 mb-1.5">
          <Icon className="w-3.5 h-3.5 text-operator-accent" />
          <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">
            {artifact.kind.replace('_', ' ')}
          </span>
          <span className="text-[10px] font-mono text-operator-muted/70">{artifact.id}</span>
          {artifact.runId && (
            <span className="text-[10px] font-mono text-operator-muted/60 ml-auto">
              {artifact.runId}
            </span>
          )}
        </div>
        <div className="text-[14px] text-operator-text font-medium leading-snug">
          {artifact.title}
        </div>
        <div className="text-[12px] text-operator-muted mt-1 leading-relaxed">
          {artifact.oneLine}
        </div>
      </div>

      {artifact.bodyMarkdown && (
        <div className="rounded-xl border border-operator-border bg-operator-bg p-3 text-[13px] text-operator-text leading-relaxed whitespace-pre-wrap">
          {artifact.bodyMarkdown}
        </div>
      )}

      {artifact.toolIds && artifact.toolIds.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5 px-0.5">
            Tools in Bundle
          </div>
          <ul className="space-y-1">
            {artifact.toolIds.map((tid, idx) => (
              <li
                key={`${tid}-${idx}`}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-operator-border bg-operator-panel/30 text-[11px]"
              >
                <Terminal className="w-3 h-3 text-operator-muted shrink-0" />
                <span className="font-mono text-operator-text">{tid}</span>
                <span className="text-operator-muted/70 ml-auto">#{idx + 1}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function BatchBody({ sessionKey, batchId }: { sessionKey: string | null; batchId: string }) {
  const batch = useMemo(() => getBatchById(sessionKey, batchId), [sessionKey, batchId]);
  if (!batch) {
    return (
      <div className="text-[12px] text-operator-muted italic">Batch not found.</div>
    );
  }
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-operator-border bg-operator-panel/40 px-3 py-2.5">
        <div className="flex items-center gap-2 mb-1.5">
          <Layers className="w-3.5 h-3.5 text-operator-accent" />
          <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">
            {batch.kind === 'read_batch' ? 'Read Batch' : 'Bundle'}
          </span>
          <span className="text-[10px] font-mono text-operator-muted/70 ml-auto">{batch.id}</span>
        </div>
        <div className="text-[14px] text-operator-text font-medium leading-snug">{batch.label}</div>
        {batch.kind === 'read_batch' && batch.mergedSummary && (
          <div className="text-[12px] text-operator-muted mt-1 leading-relaxed">
            {batch.mergedSummary}
          </div>
        )}
      </div>

      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5 px-0.5">
          Calls
        </div>
        <ul className="space-y-1">
          {batch.calls.map((c) => (
            <li
              key={c.id}
              className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg border border-operator-border bg-operator-panel/30 text-[11px]"
            >
              <Terminal className="w-3 h-3 text-operator-muted shrink-0" />
              <span className="font-mono text-operator-text">{c.toolId}</span>
              <span className="text-operator-muted truncate flex-1">{c.summary}</span>
              <span className="font-mono text-operator-muted/70 shrink-0">
                {c.durationMs}ms
              </span>
              {c.ok ? (
                <CheckCircle2 className="w-3 h-3 text-operator-success shrink-0" />
              ) : (
                <XCircle className="w-3 h-3 text-operator-error shrink-0" />
              )}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function InspectorDrawer() {
  const activeSessionKey = useAppStore((s) => s.activeSessionKey);
  const target = useAppStore((s) => s.inspectorTarget);
  const close = useAppStore((s) => s.setInspectorTarget);

  const artifact = useMemo(() => {
    if (!target) return null;
    if (target.kind === 'artifact' || target.kind === 'diff') {
      return getArtifactById(activeSessionKey, target.artifactId);
    }
    return null;
  }, [target, activeSessionKey]);

  useEffect(() => {
    if (!target) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') close(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [target, close]);

  if (!target) return null;

  const title =
    target.kind === 'diff'
      ? 'Patch Plan Inspector'
      : target.kind === 'artifact'
      ? 'Artifact Inspector'
      : 'Batch Inspector';

  const HeaderIcon = target.kind === 'diff' ? FileDiff : target.kind === 'batch' ? Layers : FileText;

  return createPortal(
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in-up"
        onClick={() => close(null)}
      />

      {/* Drawer */}
      <div className="relative ml-auto h-full w-full max-w-[640px] bg-operator-bg border-l border-operator-border shadow-shell-xl flex flex-col animate-slide-in-right">
        {/* Header */}
        <div className="flex items-center gap-2 px-4 py-3 border-b border-operator-border">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-operator-accent/10 text-operator-accent">
            <HeaderIcon className="w-3.5 h-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
              Inspector
            </div>
            <div className="text-[14px] text-operator-text font-medium truncate">
              {title}
            </div>
          </div>
          <button
            onClick={() => close(null)}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-operator-muted hover:text-operator-text hover:bg-operator-panel transition-colors duration-150"
            title="Close (Esc)"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {target.kind === 'batch' ? (
            <BatchBody sessionKey={activeSessionKey} batchId={target.batchId} />
          ) : artifact ? (
            <ArtifactBody artifact={artifact} />
          ) : (
            <div className="text-[12px] text-operator-muted italic">
              Artifact not found.
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2.5 border-t border-operator-border flex items-center justify-between bg-operator-panel/30">
          <span className="text-[10px] text-operator-muted">
            Inspector shell · future home for causal trace, diff apply, and governance actions
          </span>
          <span className="text-[10px] text-operator-muted/70 font-mono">esc to close</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
