import type React from 'react';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import {
  Activity,
  AlertTriangle,
  Box,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ClipboardCopy,
  FileDiff,
  FileText,
  FolderOpen,
  Layers,
  MessageSquareQuote,
  Package,
  Terminal,
  X,
  XCircle,
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { useArtifact, useBatch } from '../../runtime/adapter';
import type { AsyncResource, BatchResource } from '../../runtime/adapter';
import type { Artifact } from '../../runtime/types';
import type { ToolResultPart, ToolResultPreview } from '../../types/backend';
import { DiffArtifactView } from './DiffArtifactView';
import { RunInternalsDrawerBody } from './RunInternalsDrawerBody';
import { LoadingState } from './ResourceStates';
import { ChatMarkdown } from '../ChatMarkdown';
import { DiffView, FileLinesView, JsonView, PlanView } from './CodeViews';
import { langFromPath } from '../../lib/syntax';
import { formatShortMsDuration } from '../../lib/formatting';

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
    <div className="space-y-4">
      <div className="rounded-2xl border border-operator-border bg-operator-panel/30 px-3.5 py-3">
        <div className="flex items-center gap-2 mb-2">
          <span className="inline-flex h-6 w-6 items-center justify-center rounded-md bg-operator-accent/10 text-operator-accent">
            <Icon className="w-3.5 h-3.5" />
          </span>
          <span className="text-[9.5px] font-semibold uppercase tracking-[0.14em] text-operator-accent">
            {artifact.kind.replace('_', ' ')}
          </span>
          <span className="ml-auto inline-flex items-center gap-2 text-[10px] font-mono text-operator-muted/70">
            <span title={artifact.id} className="truncate max-w-[120px]">{artifact.id}</span>
            {artifact.runId && <span className="text-operator-muted/45">· {artifact.runId}</span>}
          </span>
        </div>
        <div className="text-[15px] text-operator-text font-semibold leading-snug">
          {artifact.title}
        </div>
        {artifact.oneLine && (
          <div className="text-[12px] text-operator-muted mt-1.5 leading-relaxed">
            {artifact.oneLine}
          </div>
        )}
      </div>

      {artifact.bodyMarkdown && (
        <div className="rounded-2xl border border-operator-border bg-operator-bg px-4 py-3.5">
          <ChatMarkdown content={artifact.bodyMarkdown} />
        </div>
      )}

      {artifact.toolIds && artifact.toolIds.length > 0 && (
        <div>
          <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-operator-muted mb-2 px-0.5">
            Tools in Bundle · {artifact.toolIds.length}
          </div>
          <ul className="rounded-xl border border-operator-border overflow-hidden divide-y divide-operator-border/40">
            {artifact.toolIds.map((tid, idx) => (
              <li
                key={`${tid}-${idx}`}
                className="flex items-center gap-2 px-2.5 py-1.5 text-[11px] bg-operator-panel/20"
              >
                <Terminal className="w-3 h-3 text-operator-muted/70 shrink-0" />
                <span className="font-mono text-operator-text/85 truncate">{tid}</span>
                <span className="text-operator-muted/55 ml-auto tabular-nums">#{idx + 1}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

/** Show last 2 path segments: "…/components/Foo.tsx" */
function shortPath(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  if (parts.length <= 2) return path;
  return `…/${parts.slice(-2).join('/')}`;
}

function ScopeBadge({ scope }: { scope?: 'inside_workspace' | 'outside_workspace' | null }) {
  if (!scope) return null;
  const tone =
    scope === 'outside_workspace'
      ? 'border-amber-400/30 bg-amber-400/10 text-amber-300'
      : 'border-operator-border bg-operator-panel/40 text-operator-muted';
  const label = scope === 'outside_workspace' ? 'outside home' : 'inside home';
  return (
    <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] ${tone}`}>
      {label}
    </span>
  );
}

function PolicyBadge({ decision }: { decision?: 'allowed' | 'read_roam' | 'write_blocked' | 'approval_required' | 'unsafe_unknown' | null }) {
  if (!decision || decision === 'allowed') return null;
  const tone =
    decision === 'write_blocked'
      ? 'border-operator-error/30 bg-operator-error/10 text-operator-error'
      : decision === 'approval_required'
        ? 'border-amber-400/30 bg-amber-400/10 text-amber-300'
        : decision === 'unsafe_unknown'
          ? 'border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-300'
          : 'border-sky-400/30 bg-sky-400/10 text-sky-300';
  const label =
    decision === 'write_blocked'
      ? 'write blocked'
      : decision === 'approval_required'
        ? 'approval req'
        : decision === 'unsafe_unknown'
          ? 'policy block'
          : 'read roam';
  return (
    <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] ${tone}`}>
      {label}
    </span>
  );
}

function BatchCallRow({ call }: { call: import('../../runtime/types').ActivityToolCall }) {
  const [expanded, setExpanded] = useState(false);
  const hasTarget = !!call.target;
  const hasSummary = !!call.summary && call.summary !== call.target;
  const isExpandable = hasTarget || hasSummary;
  const dur = formatShortMsDuration(call.durationMs, true);

  return (
    <li className="rounded-lg border border-operator-border bg-operator-panel/30 overflow-hidden">
        <div className="flex items-center gap-2 px-2.5 py-1.5 text-[11px]">
          {call.ok ? (
            <CheckCircle2 className="w-3 h-3 text-operator-success shrink-0" />
          ) : (
            <XCircle className="w-3 h-3 text-operator-error shrink-0" />
        )}
        {hasTarget ? (
          <span className="font-mono text-operator-accent/85 flex-1 truncate min-w-0" title={call.target!}>
            {shortPath(call.target!)}
          </span>
        ) : (
          <>
            <Terminal className="w-3 h-3 text-operator-muted/60 shrink-0" />
            <span className="font-mono text-operator-text flex-1 truncate min-w-0">{call.toolId}</span>
          </>
        )}
        <ScopeBadge scope={call.scope} />
        <PolicyBadge decision={call.policyDecision} />
        {dur && <span className="font-mono text-[10px] text-operator-muted/60 shrink-0">{dur}</span>}
        {isExpandable && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="shrink-0 text-operator-muted/50 hover:text-operator-muted transition-colors duration-100"
          >
            {expanded
              ? <ChevronDown className="w-3 h-3" />
              : <ChevronRight className="w-3 h-3" />
            }
          </button>
        )}
      </div>

      {expanded && (
        <div className="border-t border-operator-border/40 bg-operator-bg/40 px-2.5 py-2 space-y-1.5">
          {hasTarget && (
            <div className="flex items-start gap-1.5">
              <FolderOpen className="w-3 h-3 text-operator-muted/60 shrink-0 mt-0.5" />
              <span className="font-mono text-[10.5px] text-operator-muted/80 break-all">{call.target}</span>
            </div>
          )}
          {call.workspaceRoot && (
            <div className="flex items-start gap-1.5">
              <Box className="w-3 h-3 text-operator-muted/60 shrink-0 mt-0.5" />
              <div className="min-w-0">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted/45">home workspace</div>
                <div className="font-mono text-[10.5px] text-operator-muted/80 break-all">{call.workspaceRoot}</div>
              </div>
            </div>
          )}
          {hasTarget && (
            <div className="flex items-center gap-1.5">
              <Terminal className="w-3 h-3 text-operator-muted/50 shrink-0" />
              <span className="font-mono text-[10px] text-operator-muted/60">{call.toolId}</span>
            </div>
          )}
          {hasSummary && (
            <div className="text-[11px] text-operator-muted/80 leading-relaxed">{call.summary}</div>
          )}
          {call.policySummary && call.policyDecision && (
            <div className="text-[11px] text-operator-muted/80 leading-relaxed">{call.policySummary}</div>
          )}
          {!call.ok && call.error && (
            <pre className="mt-1 rounded border border-operator-error/25 bg-operator-error/5 px-2 py-1.5 text-[10.5px] font-mono text-operator-error whitespace-pre-wrap break-words">
              {call.error}
            </pre>
          )}
        </div>
      )}
    </li>
  );
}

function BatchBody({ batch }: { batch: BatchResource }) {
  // Collect unique targets from calls that have them — surfaces "what was read" prominently
  const targets = batch.calls
    .map((c) => c.target)
    .filter((t): t is string => !!t);
  const uniqueTargets = [...new Set(targets)];
  const workspaceRoot = batch.calls.find((call) => call.workspaceRoot)?.workspaceRoot || null;

  return (
    <div className="space-y-3">
      {/* Batch summary card */}
      <div className="rounded-xl border border-operator-border bg-operator-panel/40 px-3 py-2.5">
        <div className="flex items-center gap-2 mb-1.5">
          <Layers className="w-3.5 h-3.5 text-operator-accent" />
          <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">
            {batch.kind === 'read_batch' ? 'Read Batch' : 'Bundle'}
          </span>
          <span className="ml-auto text-[10px] font-mono text-operator-muted/60">{batch.id}</span>
        </div>
        <div className="text-[14px] text-operator-text font-medium leading-snug">{batch.label}</div>
        {batch.kind === 'read_batch' && batch.mergedSummary && (
          <div className="text-[12px] text-operator-muted mt-1 leading-relaxed">{batch.mergedSummary}</div>
        )}
        {workspaceRoot && (
          <div className="mt-2 rounded-lg border border-operator-border/60 bg-operator-bg/50 px-2.5 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted/45">home workspace</div>
            <div className="mt-1 font-mono text-[10.5px] text-operator-text/85 break-all">{workspaceRoot}</div>
          </div>
        )}
      </div>

      {/* Read targets — shown when backend populates RunStep.target */}
      {uniqueTargets.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5 px-0.5">
            <FolderOpen className="w-3 h-3" />
            Read Targets
          </div>
          <div className="rounded-xl border border-operator-border bg-operator-bg divide-y divide-operator-border/40 overflow-hidden">
            {uniqueTargets.map((t) => (
              <div key={t} className="flex items-center gap-2 px-2.5 py-1.5">
                <span className="font-mono text-[10.5px] text-operator-accent/80 truncate flex-1 min-w-0" title={t}>
                  {shortPath(t)}
                </span>
                <ScopeBadge scope={batch.calls.find((call) => call.target === t)?.scope} />
                <PolicyBadge decision={batch.calls.find((call) => call.target === t)?.policyDecision} />
                <span className="font-mono text-[10px] text-operator-muted/50 shrink-0 truncate max-w-[55%]" title={t}>
                  {t}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Pending target data notice — honest empty state for path visibility */}
      {uniqueTargets.length === 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-dashed border-operator-border px-2.5 py-2 text-[11px] text-operator-muted/60">
          <FolderOpen className="w-3 h-3 shrink-0" />
          <span>Read targets will appear here once the backend provides <span className="font-mono">RunStep.target</span>.</span>
        </div>
      )}

      {/* Individual calls */}
      <div>
        <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5 px-0.5">
          Calls · {batch.calls.length}
        </div>
        <ul className="space-y-1">
          {batch.calls.map((c) => (
            <BatchCallRow key={c.id} call={c} />
          ))}
        </ul>
      </div>
    </div>
  );
}

function CopyButton({ getValue }: { getValue: () => string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(getValue()).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      onClick={handleCopy}
      title="Copy to clipboard"
      className="flex items-center gap-1 rounded-md border border-operator-border/50 bg-operator-panel/30 px-1.5 py-0.5 text-[9.5px] font-medium text-operator-muted/70 transition-colors duration-100 hover:border-operator-border hover:text-operator-text"
    >
      <ClipboardCopy className="w-2.5 h-2.5" />
      {copied ? 'copied' : 'copy'}
    </button>
  );
}

function previewText(value: unknown): string {
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

function ToolBody({ tool }: { tool: ToolResultPart }) {
  const effect = tool.effect;
  const scope = tool.scope;
  const policyDecision = tool.policyDecision;
  const accessAction = tool.accessAction;
  // The preview can arrive on either field depending on which loop produced the
  // step, so normalize once. Branching on `tool.preview` alone silently fell
  // through to JsonView for every effect-carried preview — which is most of them.
  const previewValue = effect?.preview || tool.preview;
  const preview = (previewValue || null) as ToolResultPreview | null;

  // Build the 4-cell metadata grid from meaningful fields
  type MetaCell = { label: string; content: React.ReactNode };
  const cells: MetaCell[] = [];
  if (effect?.kind) cells.push({ label: 'kind', content: <span className="font-mono text-[10px] text-operator-text/80">{effect.kind}</span> });
  if (effect?.evidence_role) cells.push({ label: 'evidence', content: <span className="font-mono text-[10px] text-operator-text/80">{effect.evidence_role}</span> });
  if (scope) cells.push({ label: 'scope', content: <ScopeBadge scope={scope} /> });
  if (policyDecision && policyDecision !== 'allowed') {
    cells.push({ label: 'policy', content: <PolicyBadge decision={policyDecision} /> });
  } else if (accessAction) {
    cells.push({ label: 'access', content: <span className="font-mono text-[10px] text-operator-text/80">{accessAction}</span> });
  }

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="rounded-xl border border-operator-border bg-operator-panel/40 px-3 py-2.5">
        <div className="flex items-center gap-2 mb-1.5">
          <Terminal className="w-3.5 h-3.5 text-operator-accent" />
          <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">
            Tool Effect
          </span>
          <span className="ml-auto text-[10px] font-mono text-operator-muted/60 truncate max-w-[180px]">
            {effect?.effect_id || tool.callId}
          </span>
        </div>
        <div className="font-mono text-[13px] text-operator-text">{tool.toolId}</div>
        <div className="mt-1 text-[11px] text-operator-muted/80 leading-relaxed">{tool.summary}</div>
        {/* Trace IDs — dim, for debugging */}
        {(effect?.turn_id || effect?.decision_id) && (
          <div className="mt-2 flex items-center gap-3">
            {effect.turn_id && (
              <span className="font-mono text-[9px] text-operator-muted/30 truncate" title={effect.turn_id}>
                turn·{effect.turn_id.slice(-10)}
              </span>
            )}
            {effect.decision_id && (
              <span className="font-mono text-[9px] text-operator-muted/30 truncate" title={effect.decision_id}>
                dec·{effect.decision_id.slice(-10)}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Metadata grid — useful fields only */}
      {cells.length > 0 && (
        <div className="grid grid-cols-2 gap-2">
          {cells.map(({ label, content }) => (
            <div key={label} className="rounded-lg border border-operator-border bg-operator-bg px-2.5 py-2">
              <div className="text-[9px] uppercase tracking-wider text-operator-muted/50">{label}</div>
              <div className="mt-1">{content}</div>
            </div>
          ))}
        </div>
      )}

      {/* Target */}
      {(effect?.target || tool.target) && (
        <div className="rounded-lg border border-operator-border bg-operator-bg px-2.5 py-2">
          <div className="text-[9px] uppercase tracking-wider text-operator-muted/50">target</div>
          <div className="mt-1 font-mono text-[10.5px] text-operator-accent/85 break-all">{effect?.target || tool.target}</div>
        </div>
      )}

      {/* Policy summary */}
      {tool.policySummary && (
        <div className="rounded-lg border border-amber-400/20 bg-amber-400/5 px-2.5 py-2 text-[11px] leading-relaxed text-amber-200/80">
          {tool.policySummary}
        </div>
      )}

      {/* Preview */}
      {preview?.type === 'diff' ? (
        <DiffView preview={preview} />
      ) : preview?.type === 'plan' ? (
        <PlanView preview={preview} />
      ) : preview?.type === 'file_read' ? (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between px-0.5">
            <span className="text-[9.5px] font-semibold uppercase tracking-wider text-operator-muted/60">output</span>
            <CopyButton getValue={() => (preview?.type === 'file_read' ? preview.lines.join('\n') : '')} />
          </div>
          <FileLinesView
            lines={preview.lines}
            lang={langFromPath(preview.path)}
            startLine={preview.startLine}
            maxHeightClass="max-h-[60vh]"
          />
        </div>
      ) : preview?.type === 'raw' ? (
        // Render the body, not the envelope. This branch was missing, so a raw
        // preview fell through to JsonView and displayed
        // `{"type":"raw","text":"..."}` with every newline escaped — the result was
        // there but unreadable.
        <div className="space-y-1.5">
          <div className="flex items-center justify-between px-0.5">
            <span className="text-[9.5px] font-semibold uppercase tracking-wider text-operator-muted/60">output</span>
            <CopyButton getValue={() => (preview?.type === 'raw' ? preview.text : '')} />
          </div>
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-operator-border bg-operator-bg px-2.5 py-2 font-mono text-[10.5px] leading-5 text-operator-text/85">
            {preview.text}
          </pre>
          {preview.truncated && (
            <p className="px-0.5 text-[10px] text-operator-muted/60">
              Clipped at {preview.text.length.toLocaleString()} of{' '}
              {(preview.fullChars || 0).toLocaleString()} characters. The whole body is in
              this run's tool output artifact.
            </p>
          )}
        </div>
      ) : preview?.type === 'repo_search' ? (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between px-0.5">
            <span className="text-[9.5px] font-semibold uppercase tracking-wider text-operator-muted/60">
              {preview.matches.length} matches
            </span>
            <CopyButton getValue={() => previewText(preview)} />
          </div>
          <div className="max-h-[60vh] overflow-auto rounded-lg border border-operator-border bg-operator-bg divide-y divide-operator-border/40">
            {preview.matches.map((match, index) => (
              <div key={`${match.path}-${match.line}-${index}`} className="flex items-baseline gap-1.5 px-2.5 py-1">
                <span className="shrink-0 font-mono text-[10px] text-operator-accent">{match.path}</span>
                <span className="shrink-0 font-mono text-[10px] text-operator-muted/50">:{match.line}</span>
                <span className="min-w-0 flex-1 truncate font-mono text-[10px] text-operator-text/70">{match.snippet.trim()}</span>
              </div>
            ))}
          </div>
        </div>
      ) : previewValue ? (
        <div className="space-y-1.5">
          <div className="flex items-center justify-between px-0.5">
            <span className="text-[9.5px] font-semibold uppercase tracking-wider text-operator-muted/60">output</span>
            <CopyButton getValue={() => previewText(previewValue)} />
          </div>
          <JsonView value={previewValue} />
        </div>
      ) : null}
    </div>
  );
}

// Inline state views for the drawer body — scoped to this component so we
// can include a little contextual copy (what was being inspected) without
// making the shared ResourceStates component juggle drawer-specific props.
function DrawerState({
  icon: Icon,
  title,
  body,
  tone = 'muted',
}: {
  icon: typeof Box;
  title: string;
  body: string;
  tone?: 'muted' | 'error';
}) {
  const iconTone = tone === 'error' ? 'text-operator-error' : 'text-operator-muted';
  const bgTone = tone === 'error' ? 'bg-operator-error/10' : 'bg-operator-panel';
  return (
    <div className="flex flex-col items-center justify-center py-10 text-center">
      <div className={`mb-3 flex h-10 w-10 items-center justify-center rounded-xl ${bgTone} ${iconTone}`}>
        <Icon className="w-4 h-4" />
      </div>
      <div className="text-[13px] text-operator-text font-medium mb-1">{title}</div>
      <div className="text-[11px] text-operator-muted leading-relaxed max-w-[300px]">{body}</div>
    </div>
  );
}

function renderArtifactResource(resource: AsyncResource<Artifact>) {
  if (resource.status === 'loading') return <LoadingState label="Loading artifact…" />;
  if (resource.status === 'error') {
    return (
      <DrawerState
        icon={AlertTriangle}
        title="Could not load artifact"
        body={resource.error ?? 'Unknown error'}
        tone="error"
      />
    );
  }
  if (resource.status === 'empty' || !resource.data) {
    return (
      <DrawerState
        icon={Box}
        title="Artifact not found"
        body="This artifact may have been trimmed from the session state or never existed."
      />
    );
  }
  return <ArtifactBody artifact={resource.data} />;
}

function renderBatchResource(resource: AsyncResource<BatchResource>) {
  if (resource.status === 'loading') return <LoadingState label="Loading batch…" />;
  if (resource.status === 'error') {
    return (
      <DrawerState
        icon={AlertTriangle}
        title="Could not load batch"
        body={resource.error ?? 'Unknown error'}
        tone="error"
      />
    );
  }
  if (resource.status === 'empty' || !resource.data) {
    return (
      <DrawerState
        icon={Layers}
        title="Batch not found"
        body="This batch may have been trimmed from the session state or never existed."
      />
    );
  }
  return <BatchBody batch={resource.data} />;
}

export function InspectorDrawer() {
  const activeSessionKey = useAppStore((s) => s.activeSessionKey);
  const target = useAppStore((s) => s.inspectorTarget);
  const close = useAppStore((s) => s.setInspectorTarget);

  // Hooks always run — pass null when not the active target kind so the
  // adapter returns an empty resource cheaply. Avoids conditional hook calls.
  const artifactId = target && (target.kind === 'artifact' || target.kind === 'diff') ? target.artifactId : null;
  const batchId = target && target.kind === 'batch' ? target.batchId : null;
  const artifactResource = useArtifact(activeSessionKey, artifactId);
  const batchResource = useBatch(activeSessionKey, batchId);

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
      : target.kind === 'tool'
      ? 'Tool Inspector'
      : target.kind === 'run'
      ? 'Turn Internals'
      : 'Batch Inspector';

  const HeaderIcon = target.kind === 'diff' ? FileDiff : target.kind === 'batch' ? Layers : target.kind === 'tool' ? Terminal : target.kind === 'run' ? Activity : FileText;

  return createPortal(
    <div className="fixed inset-0 z-50 flex" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm animate-fade-in-up"
        onClick={() => close(null)}
      />

      <div className="relative ml-auto h-full w-full max-w-[680px] bg-operator-bg border-l border-operator-border shadow-shell-xl flex flex-col animate-slide-in-right">
        <div className="flex items-center gap-2.5 px-4 py-3 border-b border-operator-border">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-operator-accent/10 text-operator-accent">
            <HeaderIcon className="w-3.5 h-3.5" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[9.5px] font-semibold uppercase tracking-[0.16em] text-operator-muted/80">
              Inspector
            </div>
            <div className="mt-0.5 text-[14px] text-operator-text font-semibold truncate">
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

        <div className="flex-1 overflow-y-auto">
          {target.kind === 'run' ? (
            <RunInternalsDrawerBody sessionKey={target.sessionKey} runId={target.runId} />
          ) : (
            <div className="px-4 py-4">
              {target.kind === 'tool'
                ? <ToolBody tool={target.tool} />
                : target.kind === 'batch'
                ? renderBatchResource(batchResource)
                : renderArtifactResource(artifactResource)}
            </div>
          )}
        </div>

        <div className="px-4 py-2 border-t border-operator-border flex items-center justify-between bg-operator-panel/25">
          <span className="text-[10.5px] text-operator-muted/75">
            Paths, payloads, and causal trace
          </span>
          <span className="rounded-md border border-operator-border bg-operator-bg px-1.5 py-0.5 text-[9.5px] font-mono text-operator-muted/75">esc</span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
