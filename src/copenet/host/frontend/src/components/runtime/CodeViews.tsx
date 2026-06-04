// Shared code-rendering views: syntax-highlighted code lines, a line-numbered
// unified-diff view, and a color-coded JSON view. Used by both the inline
// transcript (InlineToolRows) and the Tool Inspector drawer so a diff/payload
// looks the same — like an editor — wherever it's shown.

import { FileDiff } from 'lucide-react';
import type { ToolResultPreview } from '../../types/backend';
import { parseUnifiedDiff, diffGutterWidth } from '../../lib/diff';
import { tokenizeLine, langFromPath, SYNTAX_CLASS } from '../../lib/syntax';

function shortPath(path: string): string {
  const parts = path.split('/');
  return parts.length > 3 ? `…/${parts.slice(-2).join('/')}` : path;
}

/** One line of source rendered with lightweight syntax highlighting. */
export function HighlightedCode({ text, lang }: { text: string; lang: string }) {
  if (!text) return <>{' '}</>;
  const tokens = tokenizeLine(text, lang);
  return (
    <>
      {tokens.map((tok, i) =>
        tok.cls === 'plain' ? (
          <span key={i}>{tok.text}</span>
        ) : (
          <span key={i} className={SYNTAX_CLASS[tok.cls]}>
            {tok.text}
          </span>
        ),
      )}
    </>
  );
}

/** Line-numbered, syntax-highlighted unified diff (no action bar). */
export function DiffView({ preview }: { preview: Extract<ToolResultPreview, { type: 'diff' }> }) {
  const displayPath = shortPath(preview.path);
  const rows = parseUnifiedDiff(preview.diff);
  const gutter = diffGutterWidth(rows);
  const lang = langFromPath(preview.path);
  const numStyle = { width: `${gutter}ch` } as const;
  return (
    <div className="mt-1.5">
      <div className="mb-1 flex items-center gap-1.5 text-[10px] text-operator-muted/60">
        <FileDiff className="h-2.5 w-2.5 shrink-0" />
        <span className="font-mono truncate">{displayPath}</span>
        {preview.created && (
          <span className="shrink-0 rounded bg-operator-success/15 px-1 text-[9px] uppercase tracking-wide text-operator-success/80">
            new
          </span>
        )}
        <span className="ml-auto shrink-0 pl-2 font-mono tabular-nums">
          <span className="text-operator-success/80">+{preview.linesAdded}</span>{' '}
          <span className="text-operator-error/80">-{preview.linesRemoved}</span>
        </span>
      </div>
      <div className="overflow-x-auto rounded-lg border border-operator-border bg-operator-bg text-[10.5px] font-mono leading-[1.65] max-h-72">
        {rows.map((row, i) => {
          if (row.kind === 'hunk') {
            return (
              <div key={i} className="bg-operator-accent/5 px-2 py-0.5 text-operator-accent/65 whitespace-pre">
                {row.text}
              </div>
            );
          }
          const rowBg =
            row.kind === 'add'
              ? 'bg-operator-success/12'
              : row.kind === 'del'
                ? 'bg-operator-error/12'
                : '';
          const marker = row.kind === 'add' ? '+' : row.kind === 'del' ? '-' : ' ';
          const markerTone =
            row.kind === 'add'
              ? 'text-operator-success/80'
              : row.kind === 'del'
                ? 'text-operator-error/80'
                : 'text-operator-muted/40';
          const gutterTone = row.kind === 'context' ? 'text-operator-muted/35' : 'text-operator-muted/55';
          return (
            <div key={i} className={`flex text-operator-text/80 ${rowBg}`}>
              <span className={`shrink-0 select-none border-r border-operator-border/40 px-1.5 text-right tabular-nums ${gutterTone}`} style={numStyle}>
                {row.oldNo ?? ''}
              </span>
              <span className={`shrink-0 select-none border-r border-operator-border/40 px-1.5 text-right tabular-nums ${gutterTone}`} style={numStyle}>
                {row.newNo ?? ''}
              </span>
              <span className={`shrink-0 select-none px-1 font-semibold ${markerTone}`}>{marker}</span>
              <span className="whitespace-pre pr-2">
                <HighlightedCode text={row.text} lang={lang} />
              </span>
            </div>
          );
        })}
      </div>
      {preview.truncated && (
        <div className="mt-0.5 px-1 text-[10px] text-operator-muted/50">Diff truncated — large change.</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// JsonView — color-coded JSON, rendered recursively (keys / strings / numbers /
// booleans / null get distinct hues) instead of a flat gray dump.
// ---------------------------------------------------------------------------

function JsonValue({ value, indent }: { value: unknown; indent: number }) {
  const pad = '  '.repeat(indent);
  const padInner = '  '.repeat(indent + 1);
  if (value === null) return <span className="text-operator-muted/60">null</span>;
  if (typeof value === 'string') return <span className="text-amber-300/90">"{value}"</span>;
  if (typeof value === 'number') return <span className="text-sky-300/90">{String(value)}</span>;
  if (typeof value === 'boolean') return <span className="text-violet-300">{String(value)}</span>;
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-operator-muted/60">[]</span>;
    return (
      <>
        <span className="text-operator-muted/60">[</span>
        {value.map((item, i) => (
          <div key={i}>
            {padInner}
            <JsonValue value={item} indent={indent + 1} />
            {i < value.length - 1 ? <span className="text-operator-muted/40">,</span> : null}
          </div>
        ))}
        <div>{pad}<span className="text-operator-muted/60">]</span></div>
      </>
    );
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-operator-muted/60">{'{}'}</span>;
    return (
      <>
        <span className="text-operator-muted/60">{'{'}</span>
        {entries.map(([key, val], i) => (
          <div key={key}>
            {padInner}
            <span className="text-operator-text/90">"{key}"</span>
            <span className="text-operator-muted/40">: </span>
            <JsonValue value={val} indent={indent + 1} />
            {i < entries.length - 1 ? <span className="text-operator-muted/40">,</span> : null}
          </div>
        ))}
        <div>{pad}<span className="text-operator-muted/60">{'}'}</span></div>
      </>
    );
  }
  return <span className="text-operator-text/80">{String(value)}</span>;
}

export function JsonView({ value }: { value: unknown }) {
  return (
    <pre className="overflow-x-auto rounded-xl border border-operator-border bg-operator-bg px-3 py-2 text-[10.5px] font-mono leading-relaxed whitespace-pre max-h-80">
      <JsonValue value={value} indent={0} />
    </pre>
  );
}
