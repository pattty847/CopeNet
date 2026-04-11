import React, { useState } from 'react';
import { Message } from '../types/backend';
import { ToolTraceCard } from './ToolTraceCard';
import { Copy, Check, User, Bot } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Spinner } from './Spinner';

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
      <div className="animate-message flex justify-center my-4">
        <div className="text-xs font-mono text-operator-muted bg-operator-panel px-3 py-1 rounded-sm border border-operator-border whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={`animate-message flex flex-col mb-6 relative ${isUser ? 'items-end' : 'items-start pl-6'}`}>
      {!isUser && <div className="absolute left-2.5 top-2 bottom-0 w-px bg-operator-border" />}
      {!isUser && <div className="absolute left-[7px] top-1.5 w-2 h-2 rounded-full bg-operator-border border-2 border-operator-bg z-10" />}

      <div className={`flex items-center gap-2 mb-1.5 px-1 ${isUser ? 'flex-row-reverse' : 'flex-row'}`}>
        <span className={`text-xs font-mono font-bold flex items-center gap-1.5 ${isUser ? 'text-operator-accent' : 'text-operator-success'}`}>
          {isUser ? <User className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
          {isUser ? 'USER COMMAND' : 'ASSISTANT'}
        </span>
        <span className="text-[10px] font-mono text-operator-muted">
          {new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>

      <div className={`group relative max-w-[85%] p-3.5 font-sans text-sm leading-relaxed border ${
        isUser
          ? 'bg-operator-panel border-operator-border text-operator-text rounded-l-md rounded-br-md'
          : 'bg-transparent border-operator-border text-operator-text rounded-md shadow-sm'
      }`}>
        <button
          onClick={handleCopy}
          className={`absolute top-2 ${isUser ? '-left-8' : '-right-8'} opacity-0 group-hover:opacity-100 transition-opacity p-1.5 text-operator-muted hover:text-operator-text bg-operator-bg border border-operator-border rounded-sm z-10`}
          title="Copy message"
        >
          {copied ? <Check className="w-3.5 h-3.5 text-operator-success" /> : <Copy className="w-3.5 h-3.5" />}
        </button>

        {!isUser && message.optimistic && !message.content ? (
          <Spinner variant="bounce" className="text-operator-muted" />
        ) : null}

        {message.content && (
          <div className="markdown-body">
            <ReactMarkdown
              remarkPlugins={[remarkGfm, remarkMath]}
              rehypePlugins={[rehypeKatex]}
              components={{
                pre: ({ children, ...props }: any) => {
                  const codeElement = React.Children.toArray(children)[0] as React.ReactElement;
                  const codeProps = (codeElement?.props || {}) as { className?: string; children?: React.ReactNode };
                  const className = codeProps.className || '';
                  const match = /language-(\w+)/.exec(className);
                  const language = match ? match[1] : 'text';
                  const codeContent = codeProps.children || '';

                  return (
                    <div className="relative group/code mt-2 mb-4 rounded-md overflow-hidden bg-[#0d0d0d] border border-operator-border">
                      <div className="flex items-center justify-between px-3 py-1.5 bg-[#1a1a1a] border-b border-operator-border text-xs text-operator-muted font-mono">
                        <span>{language}</span>
                        <button
                          onClick={() => navigator.clipboard.writeText(String(codeContent).replace(/\n$/, ''))}
                          className="hover:text-operator-text transition-colors"
                        >
                          Copy
                        </button>
                      </div>
                      <pre className="p-3 overflow-x-auto text-xs font-mono text-operator-text" {...props}>
                        {children}
                      </pre>
                    </div>
                  );
                },
                code: ({ className, children, ...props }: any) => (
                  <code className={className} {...props}>
                    {children}
                  </code>
                ),
                p: ({ children }) => <p className="mb-3 last:mb-0 leading-relaxed">{children}</p>,
                ul: ({ children }) => <ul className="list-disc pl-5 mb-3 space-y-1">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-5 mb-3 space-y-1">{children}</ol>,
                li: ({ children }) => <li>{children}</li>,
                a: ({ children, href }) => (
                  <a href={href} className="text-operator-accent hover:underline" target="_blank" rel="noreferrer">
                    {children}
                  </a>
                ),
                h1: ({ children }) => <h1 className="text-xl font-bold mb-3 mt-4 text-operator-text">{children}</h1>,
                h2: ({ children }) => <h2 className="text-lg font-bold mb-3 mt-4 text-operator-text">{children}</h2>,
                h3: ({ children }) => <h3 className="text-base font-bold mb-2 mt-3 text-operator-text">{children}</h3>,
                blockquote: ({ children }) => (
                  <blockquote className="border-l-2 border-operator-accent pl-3 italic text-operator-muted mb-3">
                    {children}
                  </blockquote>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto mb-3">
                    <table className="w-full text-left border-collapse">{children}</table>
                  </div>
                ),
                th: ({ children }) => <th className="border border-operator-border px-3 py-2 bg-operator-panel font-semibold">{children}</th>,
                td: ({ children }) => <td className="border border-operator-border px-3 py-2">{children}</td>,
              }}
            >
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {message.errorMessage && !message.content && (
          <div className="text-operator-error whitespace-pre-wrap">{message.errorMessage}</div>
        )}

        {message.toolExecution && (
          <div className="mt-3 flex flex-col gap-2">
            <ToolTraceCard trace={message.toolExecution} />
          </div>
        )}
      </div>
    </div>
  );
}
