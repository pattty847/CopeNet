// InlineToolRows — inline transcript rendering for tool call / result / batch parts.
//
// Receipt-style rendering, Claude Code/Codex aesthetic. Operator verbs, not protocol vocabulary.
// Tool inspector opens via a small text link, not a CTA button. No policy/scope badge soup.
//
//   ToolCallRow   — in-flight spinner when live; static dot when completed
//   ToolResultRow — completed tool row: verb + target, expandable preview
//   ToolBatchCard — grouped batch: "Read 4 files" / "Searched repo (3 patterns)" header

import React, { useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  XCircle,
  Loader2,
  File,
  Search,
} from 'lucide-react';
import type {
  ToolCallPart,
  ToolResultPart,
  ToolBatchPart,
  ToolBatchMember,
  ToolResultPreview,
} from '../../types/backend';
import { useAppStore } from '../../store/useAppStore';

// ---------------------------------------------------------------------------
// Operator-verb labels — replace protocol tool ids with English verbs in the UI.
// ---------------------------------------------------------------------------

const TOOL_VERB: Record<string, string> = {
  'files.read': 'Read',
  'files.list': 'Listed',
  'files.search': 'Searched',
  'files.rg': 'Searched',
  'files.write': 'Wrote',
  'files.edit': 'Edited',
  'repo.map': 'Mapped workspace',
  'test.discover': 'Discovered tests',
  'context.prepare': 'Prepared context',
  'shell.exec': 'Ran command',
  'git.diff': 'Read diff',
  'git.status': 'Read git status',
  'artifact.create': 'Saved artifact',
  'memory.list': 'Read memory',
  'memory.save': 'Saved memory',
};

function operatorVerb(toolId: string): string {
  return TOOL_VERB[toolId] || toolId;
}

function batchHeader(members: ToolBatchMember[]): string {
  if (members.length === 0) return 'Tools';
  const verbs = new Set(members.map((m) => operatorVerb(m.toolId)));
  if (verbs.size === 1) {
    const verb = members[0] ? operatorVerb(members[0].toolId) : 'Tools';
    if (verb === 'Read' && members.every((m) => m.toolId === 'files.read')) {
      return `Read ${members.length} file${members.length === 1 ? '' : 's'}`;
    }
    if (verb === 'Searched') {
      return `Searched repo (${members.length} pattern${members.length === 1 ? '' : 's'})`;
    }
    return `${verb} (${members.length})`;
  }
  return `Tools (${members.length})`;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Extract a readable one-liner from a hint string.
 * Hint may arrive as a plain string OR as JSON.stringify(arguments) from the
 * wsClient fallback. In the latter case we surface the first string value.
 */
function formatHint(hint: string | null | undefined): string | null {
  if (!hint) return null;
  const trimmed = hint.trim();
  if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
    try {
      const obj = JSON.parse(trimmed) as unknown;
      if (obj && typeof obj === 'object' && !Array.isArray(obj)) {
        const rec = obj as Record<string, unknown>;
        // Prefer 'path', 'query', 'pattern', then first string value
        for (const key of ['path', 'query', 'pattern', 'file', 'dir']) {
          if (typeof rec[key] === 'string') return String(rec[key]);
        }
        const firstStr = Object.values(rec).find((v) => typeof v === 'string');
        if (firstStr) return String(firstStr);
        // Fall back to "key: val, ..." summary (max 80 chars)
        return Object.entries(rec)
          .map(([k, v]) => `${k}:${String(v)}`)
          .join('  ')
          .slice(0, 80);
      }
    } catch {
      // Not valid JSON — fall through
    }
  }
  return trimmed.slice(0, 120);
}

/** Show last 2 path segments: "…/components/MessageBubble.tsx" */
function shortPath(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  if (parts.length <= 2) return path;
  return `…/${parts.slice(-2).join('/')}`;
}

function isFileReadMember(member: ToolBatchMember): boolean {
  return member.preview?.type === 'file_read' || member.toolId === 'files.read';
}

function fileReadLabel(member: ToolBatchMember): string {
  if (member.preview?.type === 'file_read') return member.preview.path;
  if (member.target) return member.target;
  const match = member.summary.match(/Read file\s+([^.;]+(?:\.[A-Za-z0-9_-]+)?)/i);
  return match?.[1]?.trim() || member.summary;
}

// ---------------------------------------------------------------------------
// Preview rendering
// ---------------------------------------------------------------------------

function FileReadPreviewBlock({ preview }: { preview: Extract<ToolResultPreview, { type: 'file_read' }> }) {
  const displayPath = shortPath(preview.path);
  const more = preview.totalLines != null && preview.totalLines > preview.lines.length
    ? preview.totalLines - preview.lines.length
    : null;
  return (
    <div className="mt-1.5">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] text-operator-muted/60">
        <File className="h-2.5 w-2.5 shrink-0" />
        <span className="font-mono truncate">{displayPath}</span>
        {more != null && <span className="shrink-0 ml-auto pl-2">+{more} lines</span>}
      </div>
      <pre className="overflow-x-auto rounded-lg border border-operator-border bg-operator-bg px-2.5 py-2 text-[10.5px] font-mono leading-[1.6] text-operator-text/75 whitespace-pre max-h-48">
        {preview.lines.join('\n')}
      </pre>
    </div>
  );
}

function RepoSearchPreviewBlock({ preview }: { preview: Extract<ToolResultPreview, { type: 'repo_search' }> }) {
  const more = preview.totalMatches != null && preview.totalMatches > preview.matches.length
    ? preview.totalMatches - preview.matches.length
    : null;
  return (
    <div className="mt-1.5">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] text-operator-muted/60">
        <Search className="h-2.5 w-2.5 shrink-0" />
        <span className="font-mono truncate">{preview.query}</span>
        {more != null && <span className="shrink-0 ml-auto pl-2">+{more} more</span>}
      </div>
      <div className="rounded-lg border border-operator-border bg-operator-bg divide-y divide-operator-border/40">
        {preview.matches.map((m, i) => (
          <div key={i} className="flex items-baseline gap-1.5 px-2.5 py-1 min-w-0 overflow-hidden">
            <span className="shrink-0 font-mono text-[10px] text-operator-accent truncate max-w-[55%]">{shortPath(m.path)}</span>
            <span className="shrink-0 font-mono text-[10px] text-operator-muted/50">:{m.line}</span>
            <span className="flex-1 font-mono text-[10px] text-operator-text/60 truncate">{m.snippet.trim()}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RawPreviewBlock({ preview }: { preview: Extract<ToolResultPreview, { type: 'raw' }> }) {
  return (
    <pre className="mt-1.5 overflow-x-auto rounded-lg border border-operator-border bg-operator-bg px-2.5 py-2 text-[10.5px] font-mono text-operator-text/75 whitespace-pre-wrap break-words max-h-40">
      {preview.text}
    </pre>
  );
}

function ToolPreview({ preview }: { preview: ToolResultPreview }) {
  if (preview.type === 'file_read') return <FileReadPreviewBlock preview={preview} />;
  if (preview.type === 'repo_search') return <RepoSearchPreviewBlock preview={preview} />;
  return <RawPreviewBlock preview={preview} />;
}

// ---------------------------------------------------------------------------
// ToolCallRow — durable receipt of a tool invocation
// Shows a spinner while the run is live; a static terminal icon once complete.
// ---------------------------------------------------------------------------

export function ToolCallRow({ part, isLive }: { part: ToolCallPart; isLive?: boolean }) {
  const hint = formatHint(part.target || part.hint);
  const verb = operatorVerb(part.toolId);
  return (
    <div className="flex items-center gap-2 px-1 py-1 text-[11px]">
      {isLive
        ? <Loader2 className="h-3 w-3 shrink-0 animate-spin text-operator-accent/70" />
        : <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-operator-muted/40" />
      }
      <span className="text-[11px] text-operator-muted/70 shrink-0">{verb}</span>
      {hint && (
        <span className="truncate text-[11px] text-operator-muted/55 min-w-0" title={hint}>
          {part.target ? shortPath(hint) : hint}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToolResultRow — single completed tool result
// ---------------------------------------------------------------------------

export function ToolResultRow({ part }: { part: ToolResultPart }) {
  const [expanded, setExpanded] = useState(false);
  const setInspectorTarget = useAppStore((state) => state.setInspectorTarget);
  const hasExpandable = !!part.preview || (!part.ok && !!part.error);
  const verb = operatorVerb(part.toolId);
  const targetLabel = part.target ? shortPath(part.target) : null;
  // Only render a status icon for failures — success is the default, no need to badge it
  const failed = !part.ok;

  const headerInner = (
    <>
      {failed
        ? <XCircle className="h-3 w-3 shrink-0 text-operator-error" />
        : <span className="inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-operator-muted/40" />
      }
      <span className="text-[11px] text-operator-muted/80 shrink-0">{verb}</span>
      {(targetLabel || (!part.target && part.summary)) && (
        <span className="flex-1 truncate text-[11px] text-operator-text/75 min-w-0" title={part.target || part.summary}>
          {targetLabel || part.summary}
        </span>
      )}
      {hasExpandable && (
        expanded
          ? <ChevronDown className="h-3 w-3 shrink-0 text-operator-muted/45" />
          : <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/45" />
      )}
    </>
  );

  return (
    <div className={`${failed ? 'rounded-lg border border-operator-error/25 bg-operator-error/5' : ''} overflow-hidden`}>
      {hasExpandable ? (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-2 px-1 py-1 text-left hover:bg-operator-panel/20 transition-colors duration-100 rounded"
        >
          {headerInner}
        </button>
      ) : (
        <div className="flex items-center gap-2 px-1 py-1">
          {headerInner}
        </div>
      )}

      {expanded && (
        <div className="px-2 pb-2 pt-1">
          {!part.ok && part.error && (
            <pre className="mt-1 overflow-x-auto rounded border border-operator-error/20 bg-operator-error/5 px-2.5 py-1.5 text-[10.5px] font-mono text-operator-error whitespace-pre-wrap">
              {part.error}
            </pre>
          )}
          {part.preview && <ToolPreview preview={part.preview} />}
          {part.artifactId && (
            <div className="mt-1.5">
              <button
                type="button"
                onClick={() => setInspectorTarget({ kind: 'artifact', artifactId: part.artifactId! })}
                className="text-[10.5px] text-operator-muted/70 hover:text-operator-accent transition-colors"
              >
                Inspect →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToolBatchMemberRow — compact row inside an expanded batch card
// ---------------------------------------------------------------------------

function ToolBatchMemberRow({ member }: { member: ToolBatchMember }) {
  const [expanded, setExpanded] = useState(false);
  const hasPreview = !!member.preview;
  const failed = !member.ok;
  // Show path when available via file_read preview; otherwise verb + target
  const label = member.preview?.type === 'file_read'
    ? shortPath(member.preview.path)
    : `${operatorVerb(member.toolId)}${member.target ? ` ${shortPath(member.target)}` : ''}`;

  return (
    <div className="last:border-0">
      {hasPreview ? (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-2 px-1 py-1 text-left hover:bg-operator-panel/15 transition-colors duration-100 rounded"
        >
          {failed
            ? <XCircle className="h-2.5 w-2.5 shrink-0 text-operator-error" />
            : <File className="h-2.5 w-2.5 shrink-0 text-operator-muted/45" />}
          <span className="flex-1 truncate text-[11px] text-operator-text/75 min-w-0">{label}</span>
          {expanded
            ? <ChevronDown className="h-2.5 w-2.5 shrink-0 text-operator-muted/35" />
            : <ChevronRight className="h-2.5 w-2.5 shrink-0 text-operator-muted/35" />
          }
        </button>
      ) : (
        <div className="flex items-center gap-2 px-1 py-1">
          {failed
            ? <XCircle className="h-2.5 w-2.5 shrink-0 text-operator-error" />
            : <File className="h-2.5 w-2.5 shrink-0 text-operator-muted/45" />}
          <span className="flex-1 truncate text-[11px] text-operator-text/75 min-w-0">{label}</span>
        </div>
      )}
      {expanded && hasPreview && (
        <div className="pb-1 pl-3">
          <ToolPreview preview={member.preview!} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToolBatchCard — grouped card for tool.batch (e.g. "Read 8 files")
// ---------------------------------------------------------------------------

export function ToolBatchCard({ part, isLive }: { part: ToolBatchPart; isLive?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const [showAllFiles, setShowAllFiles] = useState(false);
  const setInspectorTarget = useAppStore((state) => state.setInspectorTarget);
  const failCount = part.members.filter((m) => !m.ok).length;
  const fileReadMembers = useMemo(() => part.members.filter(isFileReadMember), [part.members]);
  const isFileReadBatch = fileReadMembers.length > 0 && fileReadMembers.length === part.members.length;
  const visibleFileMembers = showAllFiles ? fileReadMembers : fileReadMembers.slice(0, 4);
  const hiddenFileCount = Math.max(fileReadMembers.length - visibleFileMembers.length, 0);
  // Prefer derived English header over the protocol label
  const headerText = batchHeader(part.members);

  return (
    <div className="overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-1 py-1 text-left hover:bg-operator-panel/15 transition-colors duration-100 rounded"
      >
        {expanded
          ? <ChevronDown className="h-3 w-3 shrink-0 text-operator-muted/45" />
          : <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/45" />
        }
        {isLive && <Loader2 className="h-3 w-3 shrink-0 animate-spin text-operator-accent/60" />}
        <span className="flex-1 text-[11px] text-operator-text/80 font-medium truncate">{headerText}</span>
        {failCount > 0 && (
          <span className="shrink-0 text-[10px] text-operator-error">{failCount} failed</span>
        )}
      </button>

      {expanded && (
        <div className="px-2 pb-1 pt-0.5">
          {isFileReadBatch ? (
            <div className="space-y-0">
              {visibleFileMembers.map((member, i) => {
                const displayPath = shortPath(fileReadLabel(member));
                return (
                  <div key={member.callId || String(i)} className="flex items-center gap-2 py-0.5 text-[11px]">
                    <File className="h-2.5 w-2.5 shrink-0 text-operator-muted/45" />
                    <span className="min-w-0 flex-1 truncate text-operator-text/75" title={fileReadLabel(member)}>
                      {displayPath}
                    </span>
                    {!member.ok && <span className="shrink-0 text-[10px] text-operator-error">failed</span>}
                  </div>
                );
              })}
              {hiddenFileCount > 0 && (
                <button
                  type="button"
                  onClick={() => setShowAllFiles((value) => !value)}
                  className="mt-1 text-[10.5px] text-operator-muted/70 hover:text-operator-accent transition-colors"
                >
                  {showAllFiles ? 'show fewer' : `+${hiddenFileCount} more`}
                </button>
              )}
            </div>
          ) : (
            <div className="space-y-0">
              {part.members.map((member, i) => (
                <ToolBatchMemberRow
                  key={member.callId || String(i)}
                  member={member}
                />
              ))}
            </div>
          )}
          <div className="mt-1">
            <button
              type="button"
              onClick={() => setInspectorTarget({ kind: 'batch', batchId: part.batchId })}
              className="text-[10.5px] text-operator-muted/70 hover:text-operator-accent transition-colors"
            >
              Inspect →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// InlineToolPart — dispatches a single MessagePart to the right renderer.
// TextParts are rendered by the parent (as markdown).
// ToolCall rows remain in the durable transcript as a call → result receipt.
// isLive: true while the owning message is still streaming (optimistic delta).
// ---------------------------------------------------------------------------

export function InlineToolPart({
  part,
  isLive,
}: {
  part: import('../../types/backend').MessagePart;
  /** True while the message is still streaming (spinner state for tool_call rows). */
  isLive?: boolean;
}) {
  if (part.kind === 'text') return null; // rendered by parent as markdown

  if (part.kind === 'tool_call') {
    return <ToolCallRow part={part} isLive={isLive} />;
  }

  if (part.kind === 'tool_result') {
    return <ToolResultRow part={part} />;
  }

  if (part.kind === 'tool_batch') {
    return <ToolBatchCard part={part} isLive={isLive} />;
  }

  return null;
}
