// InlineToolRows — inline transcript rendering for tool call / result / batch parts.
//
// These components appear interleaved with text blocks in the assistant message bubble.
// Design: compact, operator-system aesthetic. Receipts, not feature spam.
//
//   ToolCallRow   — pulsing "calling" indicator shown while the tool is in-flight
//                   (only rendered if no matching result part exists yet for this callId)
//   ToolResultRow — completed tool row: icon + toolId + summary, expandable preview
//   ToolBatchCard — grouped batch card (tool.batch), collapsed by default
//
// Preview types (bounded, truncated at source):
//   FileReadPreview   — filename + first N lines in a code block
//   RepoSearchPreview — query + match list (path:line snippet)
//   RawPreview        — plain truncated text

import React, { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  XCircle,
  Loader2,
  File,
  Search,
  Layers,
  Terminal,
} from 'lucide-react';
import type {
  ToolCallPart,
  ToolResultPart,
  ToolBatchPart,
  ToolBatchMember,
  ToolResultPreview,
} from '../../types/backend';

// ---------------------------------------------------------------------------
// Preview rendering
// ---------------------------------------------------------------------------

function FileReadPreviewBlock({ preview }: { preview: Extract<ToolResultPreview, { type: 'file_read' }> }) {
  const filename = preview.path.split('/').pop() || preview.path;
  const more = preview.totalLines != null && preview.totalLines > preview.lines.length
    ? preview.totalLines - preview.lines.length
    : null;
  return (
    <div className="mt-1.5">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] text-operator-muted/70">
        <File className="h-2.5 w-2.5 shrink-0" />
        <span className="font-mono truncate">{filename}</span>
        {more != null && <span className="shrink-0">+{more} more lines</span>}
      </div>
      <pre className="overflow-x-auto rounded-lg border border-operator-border bg-operator-bg p-2 text-[11px] font-mono text-operator-text/80 leading-relaxed whitespace-pre">
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
      <div className="mb-1 flex items-center gap-1.5 text-[10px] text-operator-muted/70">
        <Search className="h-2.5 w-2.5 shrink-0" />
        <span className="font-mono truncate">query: {preview.query}</span>
        {more != null && <span className="shrink-0">+{more} more</span>}
      </div>
      <div className="space-y-0.5 rounded-lg border border-operator-border bg-operator-bg p-2">
        {preview.matches.map((m, i) => (
          <div key={i} className="text-[11px] font-mono leading-relaxed">
            <span className="text-operator-accent truncate">{m.path}</span>
            <span className="text-operator-muted/60">:{m.line}</span>
            <span className="ml-2 text-operator-text/70 break-all">{m.snippet}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function RawPreviewBlock({ preview }: { preview: Extract<ToolResultPreview, { type: 'raw' }> }) {
  return (
    <pre className="mt-1.5 overflow-x-auto rounded-lg border border-operator-border bg-operator-bg p-2 text-[11px] font-mono text-operator-text/80 whitespace-pre-wrap break-words">
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
// ToolCallRow — shown while the tool is in-flight
// ---------------------------------------------------------------------------

export function ToolCallRow({ part }: { part: ToolCallPart }) {
  return (
    <div className="my-1.5 flex items-center gap-2 rounded-xl border border-operator-border/60 bg-operator-bg px-3 py-2 text-[12px]">
      <Loader2 className="h-3 w-3 shrink-0 animate-spin text-operator-accent/70" />
      <span className="font-mono text-operator-muted/80 text-[11px]">{part.toolId}</span>
      {part.hint && (
        <>
          <span className="text-operator-muted/40">·</span>
          <span className="truncate text-[11px] text-operator-muted/60">{part.hint}</span>
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
  const hasPreview = !!part.preview;
  const hasError = !part.ok && !!part.error;
  const StatusIcon = part.ok ? CheckCircle2 : XCircle;
  const statusColor = part.ok ? 'text-operator-success' : 'text-operator-error';
  const borderTone = part.ok ? 'border-operator-border/60' : 'border-operator-error/20';
  const bgTone = part.ok ? 'bg-operator-bg' : 'bg-operator-error/5';

  return (
    <div className={`my-1.5 rounded-xl border ${borderTone} ${bgTone} overflow-hidden text-[12px]`}>
      <button
        onClick={() => (hasPreview || hasError) ? setExpanded(!expanded) : undefined}
        className={`flex w-full items-center gap-2 px-3 py-2 text-left ${hasPreview || hasError ? 'cursor-pointer hover:bg-operator-panel/30 transition-colors duration-100' : 'cursor-default'}`}
      >
        <StatusIcon className={`h-3 w-3 shrink-0 ${statusColor}`} />
        <span className="font-mono text-[11px] text-operator-muted/80 shrink-0">{part.toolId}</span>
        <span className="flex-1 truncate text-[11px] text-operator-muted/70">{part.summary}</span>
        {(hasPreview || hasError) && (
          expanded
            ? <ChevronDown className="h-3 w-3 shrink-0 text-operator-muted/50" />
            : <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/50" />
        )}
      </button>

      {expanded && (
        <div className="border-t border-operator-border/40 px-3 pb-3">
          {part.error && (
            <pre className="mt-2 overflow-x-auto rounded-lg border border-operator-error/20 bg-operator-error/5 p-2 text-[11px] font-mono text-operator-error whitespace-pre-wrap">
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

function ToolBatchMemberRow({ member }: { member: ToolBatchMember }) {
  const [expanded, setExpanded] = useState(false);
  const hasPreview = !!member.preview;
  const StatusIcon = member.ok ? CheckCircle2 : XCircle;
  const statusColor = member.ok ? 'text-operator-success' : 'text-operator-error';

  return (
    <div className="border-b border-operator-border/30 last:border-0">
      <button
        onClick={() => hasPreview ? setExpanded(!expanded) : undefined}
        className={`flex w-full items-center gap-2 px-3 py-1.5 text-left ${hasPreview ? 'cursor-pointer hover:bg-operator-panel/20 transition-colors duration-100' : 'cursor-default'}`}
      >
        <StatusIcon className={`h-2.5 w-2.5 shrink-0 ${statusColor}`} />
        <span className="flex-1 truncate font-mono text-[10px] text-operator-muted/80">
          {member.preview?.type === 'file_read' ? member.preview.path : member.toolId}
        </span>
        <span className="shrink-0 truncate text-[10px] text-operator-muted/50 max-w-[140px]">{member.summary}</span>
        {hasPreview && (
          expanded
            ? <ChevronDown className="h-2.5 w-2.5 shrink-0 text-operator-muted/40" />
            : <ChevronRight className="h-2.5 w-2.5 shrink-0 text-operator-muted/40" />
        )}
      </button>
      {expanded && member.preview && (
        <div className="px-3 pb-2">
          <ToolPreview preview={member.preview} />
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ToolBatchCard — grouped card for tool.batch (e.g. "Read 8 files")
// ---------------------------------------------------------------------------

export function ToolBatchCard({ part }: { part: ToolBatchPart }) {
  const [expanded, setExpanded] = useState(false);
  const failCount = part.members.filter((m) => !m.ok).length;
  const borderTone = part.ok ? 'border-operator-border/60' : 'border-operator-error/20';
  const bgTone = part.ok ? 'bg-operator-bg' : 'bg-operator-error/5';
  const StatusIcon = part.ok ? CheckCircle2 : XCircle;
  const statusColor = part.ok ? 'text-operator-success' : 'text-operator-error';

  return (
    <div className={`my-1.5 rounded-xl border ${borderTone} ${bgTone} overflow-hidden text-[12px]`}>
      {/* Header row — always visible */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-operator-panel/30 transition-colors duration-100"
      >
        {expanded
          ? <ChevronDown className="h-3 w-3 shrink-0 text-operator-muted/50" />
          : <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/50" />
        }
        <Layers className="h-3 w-3 shrink-0 text-operator-muted/60" />
        <span className="flex-1 text-[11px] text-operator-muted/80 font-medium">{part.label}</span>
        {failCount > 0 && (
          <span className="shrink-0 rounded-full bg-operator-error/10 px-1.5 py-0.5 text-[9px] font-semibold text-operator-error">
            {failCount} failed
          </span>
        )}
        <StatusIcon className={`h-3 w-3 shrink-0 ${statusColor}`} />
      </button>

      {/* Member list — shown when expanded */}
      {expanded && (
        <div className="border-t border-operator-border/40">
          {part.members.map((member) => (
            <ToolBatchMemberRow key={member.callId} member={member} />
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// InlinePartRenderer — renders a single MessagePart from the parts array.
// TextParts are rendered separately by the parent (as markdown blocks).
// ToolCall rows remain visible even after results arrive so the transcript
// shows "call → result" as a durable sequence.
// ---------------------------------------------------------------------------

export function InlineToolPart({
  part,
}: {
  part: import('../../types/backend').MessagePart;
}) {
  if (part.kind === 'text') return null; // rendered by parent as markdown

  if (part.kind === 'tool_call') {
    return <ToolCallRow part={part} />;
  }

  if (part.kind === 'tool_result') {
    return <ToolResultRow part={part} />;
  }

  if (part.kind === 'tool_batch') {
    return <ToolBatchCard part={part} />;
  }

  return null;
}
