import React, { useState } from 'react';
import { Message } from '../types/backend';
import { ToolTraceCard } from './ToolTraceCard';
import { InlineToolPart } from './transcript/InlineToolRows';
import { Copy, Check } from 'lucide-react';
import { Spinner } from './Spinner';
import { ChatMarkdown } from './ChatMarkdown';
import type { MessagePart, ToolBatchPart, ToolCallPart, ToolResultPart } from '../types/backend';

function partsShouldCollapseIntoSingleRow(current: ToolCallPart, next: ToolResultPart | ToolBatchPart): boolean {
  if (next.kind === 'tool_result') {
    if (current.callId && next.callId && current.callId === next.callId) return true;
    return current.toolId === next.toolId;
  }
  if (next.kind === 'tool_batch') {
    return current.toolId === 'tool.batch';
  }
  return false;
}

export function collapseRenderedMessageParts(parts: MessagePart[]): MessagePart[] {
  const collapsed: MessagePart[] = [];
  for (let index = 0; index < parts.length; index += 1) {
    const current = parts[index];
    if (current.kind === 'tool_call') {
      const next = parts[index + 1];
      if (
        next &&
        (next.kind === 'tool_result' || next.kind === 'tool_batch') &&
        partsShouldCollapseIntoSingleRow(current, next)
      ) {
        continue;
      }
    }
    collapsed.push(current);
  }
  return collapsed;
}

// PartsBody — renders a structured parts array with interleaved tool rows.
function PartsBody({ parts, isLive }: { parts: NonNullable<Message['parts']>; isLive?: boolean }) {
  const renderParts = collapseRenderedMessageParts(parts);
  return (
    <div className="space-y-2">
      {renderParts.map((part, i) => {
        if (part.kind === 'text') {
          if (!part.content) return null;
          return <ChatMarkdown key={i} content={part.content} />;
        }
        return <InlineToolPart key={i} part={part} isLive={isLive} />;
      })}
    </div>
  );
}

function formatTimestamp(ts: string) {
  return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  if (isSystem) {
    return (
      <div className="animate-message my-3 flex justify-center">
        <div className="px-3 py-1 text-[11px] text-operator-muted border border-operator-border/60 rounded-full whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  if (isUser) {
    return (
      <div className="animate-message group relative flex w-full justify-end pb-4">
        <div className="relative max-w-[80%] min-w-0">
          <div className="rounded-2xl rounded-br-md border border-operator-accent/15 bg-operator-accent/5 px-3.5 py-2 text-[13.5px] leading-relaxed text-operator-text font-sans break-words">
            {message.content && <ChatMarkdown content={message.content} density="compact" />}
          </div>
          <div className="mt-1 flex items-center justify-end gap-1.5 px-1 text-[10px] text-operator-muted/70">
            <button
              onClick={handleCopy}
              className="opacity-0 transition-opacity duration-150 group-hover:opacity-100 inline-flex items-center gap-0.5 hover:text-operator-text"
              title="Copy message"
            >
              {copied ? <Check className="w-3 h-3 text-operator-success" /> : <Copy className="w-3 h-3" />}
            </button>
            <span className="tabular-nums">{formatTimestamp(message.timestamp)}</span>
          </div>
        </div>
      </div>
    );
  }

  // Assistant
  return (
    <div className="animate-message group relative flex w-full pb-5 pl-4">
      <div className="absolute left-2 top-2 bottom-2 w-px bg-operator-border/55" />
      <div className="absolute left-[5px] top-2 w-2 h-2 rounded-full bg-operator-accent/60 ring-2 ring-operator-bg z-10" />

      <div className="relative min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2 px-1 text-[10px] font-medium uppercase tracking-[0.14em] text-operator-muted/85">
          <span>Assistant</span>
          <span className="tabular-nums text-operator-muted/55">{formatTimestamp(message.timestamp)}</span>
          <button
            onClick={handleCopy}
            className="ml-auto inline-flex items-center gap-1 opacity-0 transition-opacity duration-150 group-hover:opacity-100 hover:text-operator-text"
            title="Copy message"
          >
            {copied ? <Check className="w-3 h-3 text-operator-success" /> : <Copy className="w-3 h-3" />}
          </button>
        </div>

        <div className="px-1 text-[13.5px] leading-relaxed text-operator-text font-sans break-words">
          {message.optimistic && !message.content && !message.parts?.length ? (
            <Spinner variant="bounce" className="text-operator-muted" />
          ) : null}

          {message.parts && message.parts.length > 0 ? (
            <PartsBody parts={message.parts} isLive={!!(message.optimistic && message.state === 'delta')} />
          ) : (
            <>
              {message.content && <ChatMarkdown content={message.content} />}
              {message.toolExecution && (
                <div className="mt-2.5 flex flex-col gap-1.5">
                  <ToolTraceCard trace={message.toolExecution} />
                </div>
              )}
            </>
          )}

          {message.errorMessage && !message.content && !message.parts?.length && (
            <div className="rounded-lg border border-operator-error/25 bg-operator-error/5 px-3 py-2 text-[12.5px] text-operator-error whitespace-pre-wrap">
              {message.errorMessage}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
