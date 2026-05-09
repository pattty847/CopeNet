import React, { useState } from 'react';
import { Message } from '../types/backend';
import { ToolTraceCard } from './ToolTraceCard';
import { InlineToolPart } from './transcript/InlineToolRows';
import { Copy, Check, User, Bot } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Spinner } from './Spinner';
import type { MessagePart, ToolBatchPart, ToolCallPart, ToolResultPart } from '../types/backend';

// ---------------------------------------------------------------------------
// Shared markdown renderer — used for both legacy content and TextParts.
// ---------------------------------------------------------------------------
const MD_COMPONENTS: React.ComponentProps<typeof ReactMarkdown>['components'] = {
  pre: ({ children, ...props }: any) => {
    const codeElement = React.Children.toArray(children)[0] as React.ReactElement;
    const codeProps = (codeElement?.props || {}) as { className?: string; children?: React.ReactNode };
    const className = codeProps.className || '';
    const match = /language-(\w+)/.exec(className);
    const language = match ? match[1] : 'text';
    const codeContent = codeProps.children || '';
    return (
      <div className="relative group/code mt-2 mb-3 rounded-xl overflow-hidden border" style={{ backgroundColor: 'var(--color-code-bg)', borderColor: 'var(--color-code-border)' }}>
        <div className="flex items-center justify-between px-3 py-1.5 border-b text-[10px]" style={{ backgroundColor: 'var(--color-code-header)', borderColor: 'var(--color-code-border)', color: 'var(--color-code-text)', opacity: 0.6 }}>
          <span className="font-semibold">{language}</span>
          <button
            onClick={() => navigator.clipboard.writeText(String(codeContent).replace(/\n$/, ''))}
            className="opacity-70 hover:opacity-100 transition-opacity duration-150"
          >
            Copy
          </button>
        </div>
        <pre className="p-3 overflow-x-auto text-[12px] font-mono" style={{ color: 'var(--color-code-text)' }} {...props}>
          {children}
        </pre>
      </div>
    );
  },
  code: ({ className, children, ...props }: any) => (
    <code className={className} {...props}>{children}</code>
  ),
  p: ({ children }) => <p className="mb-2.5 last:mb-0 leading-relaxed break-words">{children}</p>,
  ul: ({ children }) => <ul className="list-disc pl-4 mb-2.5 space-y-0.5">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-4 mb-2.5 space-y-0.5">{children}</ol>,
  li: ({ children }) => <li>{children}</li>,
  a: ({ children, href }) => (
    <a href={href} className="text-operator-accent hover:underline" target="_blank" rel="noreferrer">{children}</a>
  ),
  h1: ({ children }) => <h1 className="text-lg font-bold mb-2.5 mt-3 text-operator-text">{children}</h1>,
  h2: ({ children }) => <h2 className="text-[15px] font-bold mb-2.5 mt-3 text-operator-text">{children}</h2>,
  h3: ({ children }) => <h3 className="text-[14px] font-bold mb-2 mt-2.5 text-operator-text">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-operator-accent pl-3 italic text-operator-muted mb-2.5 break-words">{children}</blockquote>
  ),
  table: ({ children }) => (
    <div className="overflow-x-auto mb-2.5">
      <table className="w-full text-left border-collapse">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-operator-border px-2.5 py-1.5 bg-operator-panel font-semibold text-[12px]">{children}</th>,
  td: ({ children }) => <td className="border border-operator-border px-2.5 py-1.5 text-[12px]">{children}</td>,
};

function MarkdownBody({ content }: { content: string }) {
  return (
    <div className="markdown-body break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={MD_COMPONENTS}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

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

// ---------------------------------------------------------------------------
// PartsBody — renders a structured parts array with interleaved tool rows.
// ToolCallParts remain visible as durable call → result receipts (audit trail).
// ---------------------------------------------------------------------------
function PartsBody({ parts, isLive }: { parts: NonNullable<Message['parts']>; isLive?: boolean }) {
  const renderParts = collapseRenderedMessageParts(parts);
  return (
    <div className="space-y-2">
      {renderParts.map((part, i) => {
        if (part.kind === 'text') {
          if (!part.content) return null;
          return <MarkdownBody key={i} content={part.content} />;
        }
        return (
          <InlineToolPart key={i} part={part} isLive={isLive} />
        );
      })}
    </div>
  );
}

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';
  const isSystem = message.role === 'system';
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(message.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (isSystem) {
    return (
      <div className="animate-message flex justify-center my-3">
        <div className="text-[11px] text-operator-muted px-3 py-1 border border-operator-border/60 whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={`animate-message flex flex-col mb-4 relative ${isUser ? 'items-end' : 'items-start pl-4'}`}>
      {!isUser && <div className="absolute left-2 top-2 bottom-0 w-px bg-operator-border/70" />}
      {!isUser && <div className="absolute left-[5px] top-1.5 w-2 h-2 rounded-full bg-operator-border border-2 border-operator-bg z-10" />}

      <div className={`flex items-center gap-1.5 mb-1 px-1 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <span className={`text-[10px] font-semibold flex items-center gap-1 uppercase tracking-wider ${isUser ? 'text-operator-accent' : 'text-operator-success'}`}>
          {isUser ? <User className="w-3 h-3" /> : <Bot className="w-3 h-3" />}
          {isUser ? 'User Command' : 'Assistant'}
        </span>
        <span className="text-[10px] text-operator-muted/60">
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>

      <div className={`group relative w-full px-3 py-2.5 font-sans text-[13px] leading-relaxed overflow-hidden ${
        isUser
          ? 'bg-operator-panel/22 border border-operator-border/60 text-operator-text rounded-[18px] rounded-br-md'
          : 'bg-transparent border-b border-operator-border/55 text-operator-text'
      }`}>
        <button
          onClick={handleCopy}
          className={`absolute top-2 ${isUser ? '-left-7' : '-right-7'} opacity-0 group-hover:opacity-100 transition-all duration-150 p-1 text-operator-muted hover:text-operator-text bg-operator-bg border border-operator-border/70 rounded-md z-10`}
          title="Copy message"
        >
          {copied ? <Check className="w-3 h-3 text-operator-success" /> : <Copy className="w-3 h-3" />}
        </button>

        {!isUser && message.optimistic && !message.content && !message.parts?.length ? (
          <Spinner variant="bounce" className="text-operator-muted" />
        ) : null}

        {/* Parts path — structured interleaved text + tool rows */}
        {message.parts && message.parts.length > 0 ? (
          <PartsBody parts={message.parts} isLive={!!(message.optimistic && message.state === 'delta')} />
        ) : (
          <>
            {/* Legacy path — plain content + single ToolTraceCard at end */}
            {message.content && <MarkdownBody content={message.content} />}
            {message.toolExecution && (
              <div className="mt-2.5 flex flex-col gap-1.5">
                <ToolTraceCard trace={message.toolExecution} />
              </div>
            )}
          </>
        )}

        {message.errorMessage && !message.content && !message.parts?.length && (
          <div className="text-operator-error whitespace-pre-wrap">{message.errorMessage}</div>
        )}
      </div>
    </div>
  );
}
