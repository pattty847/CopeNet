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
      <div className="animate-message flex justify-center my-3">
        <div className="text-[11px] text-operator-muted bg-operator-panel px-3 py-1 rounded-lg border border-operator-border whitespace-pre-wrap">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className={`animate-message flex flex-col mb-5 relative ${isUser ? 'items-end' : 'items-start pl-5'}`}>
      {!isUser && <div className="absolute left-2 top-2 bottom-0 w-px bg-operator-border" />}
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

      <div className={`group relative max-w-[85%] p-3 font-sans text-[13px] leading-relaxed border overflow-hidden ${
        isUser
          ? 'bg-operator-panel border-operator-border text-operator-text rounded-2xl rounded-br-md'
          : 'bg-transparent border-operator-border text-operator-text rounded-2xl shadow-sm'
      }`}>
        <button
          onClick={handleCopy}
          className={`absolute top-2 ${isUser ? '-left-7' : '-right-7'} opacity-0 group-hover:opacity-100 transition-all duration-150 p-1 text-operator-muted hover:text-operator-text bg-operator-bg border border-operator-border rounded-lg z-10`}
          title="Copy message"
        >
          {copied ? <Check className="w-3 h-3 text-operator-success" /> : <Copy className="w-3 h-3" />}
        </button>

        {!isUser && message.optimistic && !message.content ? (
          <Spinner variant="bounce" className="text-operator-muted" />
        ) : null}

        {message.content && (
          <div className="markdown-body break-words">
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
                  <code className={className} {...props}>
                    {children}
                  </code>
                ),
                p: ({ children }) => <p className="mb-2.5 last:mb-0 leading-relaxed break-words">{children}</p>,
                ul: ({ children }) => <ul className="list-disc pl-4 mb-2.5 space-y-0.5">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal pl-4 mb-2.5 space-y-0.5">{children}</ol>,
                li: ({ children }) => <li>{children}</li>,
                a: ({ children, href }) => (
                  <a href={href} className="text-operator-accent hover:underline" target="_blank" rel="noreferrer">
                    {children}
                  </a>
                ),
                h1: ({ children }) => <h1 className="text-lg font-bold mb-2.5 mt-3 text-operator-text">{children}</h1>,
                h2: ({ children }) => <h2 className="text-[15px] font-bold mb-2.5 mt-3 text-operator-text">{children}</h2>,
                h3: ({ children }) => <h3 className="text-[14px] font-bold mb-2 mt-2.5 text-operator-text">{children}</h3>,
                blockquote: ({ children }) => (
                  <blockquote className="border-l-2 border-operator-accent pl-3 italic text-operator-muted mb-2.5 break-words">
                    {children}
                  </blockquote>
                ),
                table: ({ children }) => (
                  <div className="overflow-x-auto mb-2.5">
                    <table className="w-full text-left border-collapse">{children}</table>
                  </div>
                ),
                th: ({ children }) => <th className="border border-operator-border px-2.5 py-1.5 bg-operator-panel font-semibold text-[12px]">{children}</th>,
                td: ({ children }) => <td className="border border-operator-border px-2.5 py-1.5 text-[12px]">{children}</td>,
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
          <div className="mt-2.5 flex flex-col gap-1.5">
            <ToolTraceCard trace={message.toolExecution} />
          </div>
        )}
      </div>
    </div>
  );
}
