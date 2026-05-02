// InlineToolRows — inline transcript rendering for tool call / result / batch parts.
//
// These components appear interleaved with text blocks in the assistant message bubble.
// Design: compact, operator-system aesthetic. Receipts, not feature spam.
//
//   ToolCallRow   — in-flight spinner when live; static receipt icon when completed
//   ToolResultRow — completed tool row: icon + toolId + summary, expandable preview
//   ToolBatchCard — grouped batch card (tool.batch), collapsed by default
//
// Preview types (bounded, truncated at source):
//   FileReadPreview   — path (last 2 segments) + first N lines in a code block
//   RepoSearchPreview — query + match list (path:line  snippet, truncated)
//   RawPreview        — plain truncated text

import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Loader2,
  Terminal,
  File,
  Search,
  Layers,
} from 'lucide-react';
import type {
  ToolCallPart,
  ToolResultPart,
  ToolBatchPart,
  ToolBatchMember,
  ToolResultPreview,
} from '../../types/backend';

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
  const hint = formatHint(part.hint);
  return (
    <div className="flex items-center gap-2 rounded-lg border border-operator-border/40 bg-operator-bg/60 px-2.5 py-1.5 text-[11px]">
      {isLive
        ? <Loader2 className="h-3 w-3 shrink-0 animate-spin text-operator-accent/60" />
        : <Terminal className="h-3 w-3 shrink-0 text-operator-muted/40" />
      }
      <span className="font-mono text-[10.5px] text-operator-muted/70 shrink-0">{part.toolId}</span>
      {hint && (
        <>
          <span className="text-operator-muted/30">·</span>
          <span className="truncate text-[10.5px] text-operator-muted/50 min-w-0">{hint}</span>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToolResultRow — single completed tool result
// ---------------------------------------------------------------------------

export function ToolResultRow({ part }: { part: ToolResultPart }) {
  const [expanded, setExpanded] = useState(false);
  const hasExpandable = !!part.preview || (!part.ok && !!part.error);
  const StatusIcon = part.ok ? CheckCircle2 : XCircle;
  const statusColor = part.ok ? 'text-operator-success' : 'text-operator-error';
  const borderTone = part.ok ? 'border-operator-border/50' : 'border-operator-error/25';
  const bgTone = part.ok ? 'bg-operator-bg/60' : 'bg-operator-error/5';

  return (
    <div className={`rounded-lg border ${borderTone} ${bgTone} overflow-hidden`}>
      {hasExpandable ? (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left hover:bg-operator-panel/20 transition-colors duration-100"
        >
          <StatusIcon className={`h-3 w-3 shrink-0 ${statusColor}`} />
          <span className="font-mono text-[10.5px] text-operator-muted/70 shrink-0">{part.toolId}</span>
          <span className="flex-1 truncate text-[10.5px] text-operator-muted/60 min-w-0">{part.summary}</span>
          {expanded
            ? <ChevronDown className="h-3 w-3 shrink-0 text-operator-muted/40" />
            : <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/40" />
          }
        </button>
      ) : (
        <div className="flex items-center gap-2 px-2.5 py-1.5">
          <StatusIcon className={`h-3 w-3 shrink-0 ${statusColor}`} />
          <span className="font-mono text-[10.5px] text-operator-muted/70 shrink-0">{part.toolId}</span>
          <span className="flex-1 truncate text-[10.5px] text-operator-muted/60 min-w-0">{part.summary}</span>
        </div>
      )}

      {expanded && (
        <div className="border-t border-operator-border/30 px-2.5 pb-2.5">
          {!part.ok && part.error && (
            <pre className="mt-2 overflow-x-auto rounded-lg border border-operator-error/20 bg-operator-error/5 px-2.5 py-1.5 text-[10.5px] font-mono text-operator-error whitespace-pre-wrap">
              {part.error}
            </pre>
          )}
          {part.preview && <ToolPreview preview={part.preview} />}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToolBatchMemberRow — compact row inside an expanded batch card
// ---------------------------------------------------------------------------

function ToolBatchMemberRow({ member, index }: { member: ToolBatchMember; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const hasPreview = !!member.preview;
  const StatusIcon = member.ok ? CheckCircle2 : XCircle;
  const statusColor = member.ok ? 'text-operator-success' : 'text-operator-error';
  // Show full path when available via file_read preview; otherwise toolId
  const label = member.preview?.type === 'file_read'
    ? shortPath(member.preview.path)
    : member.toolId;

  return (
    <div className="border-b border-operator-border/25 last:border-0">
      {hasPreview ? (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex w-full items-center gap-2 px-3 py-1.5 text-left hover:bg-operator-panel/15 transition-colors duration-100"
        >
          <StatusIcon className={`h-2.5 w-2.5 shrink-0 ${statusColor}`} />
          <span className="flex-1 truncate font-mono text-[10px] text-operator-muted/75 min-w-0">{label}</span>
          <span className="shrink-0 truncate text-[10px] text-operator-muted/45 max-w-[45%]">{member.summary}</span>
          {expanded
            ? <ChevronDown className="h-2.5 w-2.5 shrink-0 text-operator-muted/35" />
            : <ChevronRight className="h-2.5 w-2.5 shrink-0 text-operator-muted/35" />
          }
        </button>
      ) : (
        <div className="flex items-center gap-2 px-3 py-1.5">
          <StatusIcon className={`h-2.5 w-2.5 shrink-0 ${statusColor}`} />
          <span className="flex-1 truncate font-mono text-[10px] text-operator-muted/75 min-w-0">{label}</span>
          <span className="shrink-0 text-[10px] text-operator-muted/45">{member.summary}</span>
        </div>
      )}
      {expanded && hasPreview && (
        <div className="px-3 pb-2">
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
  const failCount = part.members.filter((m) => !m.ok).length;
  const borderTone = part.ok ? 'border-operator-border/50' : 'border-operator-error/25';
  const bgTone = part.ok ? 'bg-operator-bg/60' : 'bg-operator-error/5';
  const StatusIcon = part.ok ? CheckCircle2 : XCircle;
  const statusColor = part.ok ? 'text-operator-success' : 'text-operator-error';

  return (
    <div className={`rounded-lg border ${borderTone} ${bgTone} overflow-hidden`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left hover:bg-operator-panel/20 transition-colors duration-100"
      >
        {expanded
          ? <ChevronDown className="h-3 w-3 shrink-0 text-operator-muted/40" />
          : <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/40" />
        }
        {isLive
          ? <Loader2 className="h-3 w-3 shrink-0 animate-spin text-operator-accent/50" />
          : <Layers className="h-3 w-3 shrink-0 text-operator-muted/50" />
        }
        <span className="flex-1 text-[10.5px] text-operator-muted/75 font-medium">{part.label}</span>
        {failCount > 0 && (
          <span className="shrink-0 rounded-full bg-operator-error/10 px-1.5 py-0.5 text-[9px] font-semibold text-operator-error">
            {failCount} failed
          </span>
        )}
        <StatusIcon className={`h-3 w-3 shrink-0 ${statusColor}`} />
      </button>

      {expanded && (
        <div className="border-t border-operator-border/30">
          {part.members.map((member, i) => (
            <ToolBatchMemberRow
              key={member.callId || String(i)}
              member={member}
              index={i}
            />
          ))}
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
