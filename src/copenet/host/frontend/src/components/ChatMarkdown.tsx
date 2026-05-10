import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Check, Copy } from 'lucide-react';

type Density = 'cozy' | 'compact';

function CodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(code.replace(/\n$/, ''));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };
  return (
    <div
      className="relative group/code my-3 rounded-xl overflow-hidden border"
      style={{ backgroundColor: 'var(--color-code-bg)', borderColor: 'var(--color-code-border)' }}
    >
      <div
        className="flex items-center justify-between px-3 py-1.5 border-b text-[10px]"
        style={{ backgroundColor: 'var(--color-code-header)', borderColor: 'var(--color-code-border)', color: 'var(--color-code-text)', opacity: 0.72 }}
      >
        <span className="font-semibold tracking-wide uppercase">{language}</span>
        <button
          onClick={handleCopy}
          className="inline-flex items-center gap-1 opacity-70 hover:opacity-100 transition-opacity duration-150"
          title="Copy code"
        >
          {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>
      <pre
        className="p-3 overflow-x-auto text-[12px] font-mono leading-relaxed"
        style={{ color: 'var(--color-code-text)' }}
      >
        <code>{code}</code>
      </pre>
    </div>
  );
}

function makeComponents(density: Density): React.ComponentProps<typeof ReactMarkdown>['components'] {
  const pTight = density === 'compact';
  return {
    pre: ({ children }: any) => {
      const codeElement = React.Children.toArray(children)[0] as React.ReactElement;
      const codeProps = (codeElement?.props || {}) as { className?: string; children?: React.ReactNode };
      const className = codeProps.className || '';
      const match = /language-(\w+)/.exec(className);
      const language = match ? match[1] : 'text';
      const codeContent = String(codeProps.children ?? '');
      return <CodeBlock language={language} code={codeContent} />;
    },
    code: ({ className, children, ...props }: any) => (
      <code className={className} {...props}>{children}</code>
    ),
    p: ({ children }) => (
      <p className={`${pTight ? 'mb-2' : 'mb-2.5'} last:mb-0 leading-relaxed break-words`}>{children}</p>
    ),
    ul: ({ children }) => <ul className="list-disc pl-5 mb-2.5 space-y-0.5 marker:text-operator-muted/50">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal pl-5 mb-2.5 space-y-0.5 marker:text-operator-muted/60">{children}</ol>,
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    a: ({ children, href }) => (
      <a
        href={href}
        className="text-operator-accent underline-offset-2 decoration-operator-accent/40 hover:decoration-operator-accent transition-colors"
        target="_blank"
        rel="noreferrer"
      >
        {children}
      </a>
    ),
    h1: ({ children }) => (
      <h1 className="text-[18px] font-semibold mt-4 mb-2 text-operator-text tracking-tight first:mt-0">{children}</h1>
    ),
    h2: ({ children }) => (
      <h2 className="text-[15px] font-semibold mt-3.5 mb-2 text-operator-text tracking-tight first:mt-0">{children}</h2>
    ),
    h3: ({ children }) => (
      <h3 className="text-[13.5px] font-semibold mt-3 mb-1.5 text-operator-text tracking-tight first:mt-0">{children}</h3>
    ),
    h4: ({ children }) => (
      <h4 className="text-[12.5px] font-semibold mt-2.5 mb-1 uppercase tracking-[0.08em] text-operator-muted first:mt-0">{children}</h4>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-2 border-l-2 border-operator-accent/60 pl-3 italic text-operator-muted/95 break-words">
        {children}
      </blockquote>
    ),
    hr: () => <hr className="my-3 border-operator-border/50" />,
    table: ({ children }) => (
      <div className="overflow-x-auto my-3 rounded-lg border border-operator-border">
        <table className="w-full text-left border-collapse">{children}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-operator-panel/40">{children}</thead>,
    th: ({ children }) => (
      <th className="border-b border-operator-border px-2.5 py-1.5 font-semibold text-[11.5px] text-operator-text">{children}</th>
    ),
    td: ({ children }) => (
      <td className="border-b border-operator-border/50 px-2.5 py-1.5 text-[12px] text-operator-text/90">{children}</td>
    ),
  };
}

const COZY_COMPONENTS = makeComponents('cozy');
const COMPACT_COMPONENTS = makeComponents('compact');

export function ChatMarkdown({ content, density = 'cozy' }: { content: string; density?: Density }) {
  return (
    <div className="markdown-body break-words">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={density === 'compact' ? COMPACT_COMPONENTS : COZY_COMPONENTS}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
