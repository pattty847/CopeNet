import React, { useMemo, useState } from 'react';
import { ChevronDown, ChevronRight, Terminal, CheckCircle2, XCircle, File } from 'lucide-react';
import { ToolExecution } from '../types/backend';

function extractReadFiles(summary: string): string[] {
  const matches = [...summary.matchAll(/Read file\s+([^.;]+(?:\.[A-Za-z0-9_-]+)?)/gi)];
  return matches.map((match) => match[1]?.trim()).filter(Boolean) as string[];
}

function shortPath(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  if (parts.length <= 2) return path;
  return `…/${parts.slice(-2).join('/')}`;
}

export function ToolTraceCard({ trace }: { trace: ToolExecution }) {
  const [expanded, setExpanded] = useState(false);
  const [showAllFiles, setShowAllFiles] = useState(false);
  const statusColor = trace.ok ? 'text-operator-success' : 'text-operator-error';
  const StatusIcon = trace.ok ? CheckCircle2 : XCircle;
  const summary = trace.summary?.trim() || (trace.ok ? 'Tool completed successfully.' : 'Tool execution failed.');
  const cardTone = trace.ok ? 'border-operator-border/55 bg-operator-bg/35' : 'border-operator-error/25 bg-operator-error/5';
  const readFiles = useMemo(() => extractReadFiles(summary), [summary]);
  const visibleFiles = showAllFiles ? readFiles : readFiles.slice(0, 4);
  const hiddenFileCount = Math.max(readFiles.length - visibleFiles.length, 0);
  const hasInlineFiles = trace.toolId === 'tool.batch' && readFiles.length > 0;

  return (
    <div className={`rounded-lg border overflow-hidden text-[12px] ${cardTone}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left transition-colors duration-150 hover:bg-operator-panel/30"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 shrink-0 text-operator-muted/60" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0 text-operator-muted/60" />
        )}
        <Terminal className="h-3 w-3 shrink-0 text-operator-muted/60" />
        <span className="shrink-0 font-mono text-[10.5px] text-operator-muted/85">{trace.toolId}</span>
        <span className="min-w-0 flex-1 truncate text-[10.5px] text-operator-muted/85">
          {hasInlineFiles ? `${readFiles.length} file${readFiles.length === 1 ? '' : 's'} read` : summary}
        </span>
        <StatusIcon className={`h-3 w-3 shrink-0 ${statusColor}`} />
      </button>

      {expanded && (
        <div className="px-2.5 py-2 border-t border-operator-border/40 bg-operator-panel/10 overflow-x-auto">
          {hasInlineFiles ? (
            <div className="mb-2.5">
              <div className="text-operator-muted mb-1 text-[9px] font-semibold tracking-wider uppercase">Files Read</div>
              <div className="space-y-1">
                {visibleFiles.map((file, index) => (
                  <div key={`${file}-${index}`} className="flex items-center gap-2 text-[11px]">
                    <File className="h-2.5 w-2.5 shrink-0 text-operator-muted/60" />
                    <span className="min-w-0 truncate font-mono text-operator-text/82" title={file}>{shortPath(file)}</span>
                  </div>
                ))}
                {hiddenFileCount > 0 && (
                  <button
                    type="button"
                    onClick={() => setShowAllFiles((value) => !value)}
                    className="pt-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-operator-accent transition-colors duration-150 hover:text-operator-text"
                  >
                    {showAllFiles ? 'show fewer' : `+${hiddenFileCount} more`}
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="mb-2.5">
              <div className="text-operator-muted mb-1 text-[9px] font-semibold tracking-wider uppercase">Summary</div>
              <pre className="text-operator-text text-[11px] bg-operator-bg/45 p-2 border border-operator-border/50 whitespace-pre-wrap">
                {summary}
              </pre>
            </div>
          )}
          {trace.error && (
            <div>
              <div className="mb-1 text-[9px] font-semibold tracking-wider uppercase text-operator-error">Error</div>
              <pre className="text-[11px] bg-operator-bg/45 p-2 border border-operator-error/25 text-operator-error whitespace-pre-wrap">
                {trace.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
