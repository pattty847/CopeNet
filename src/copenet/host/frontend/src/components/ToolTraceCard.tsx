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
    <div className={`border border-x-0 overflow-hidden text-[12px] ${cardTone}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start justify-between px-2.5 py-2 hover:bg-operator-panel/18 transition-colors duration-150 text-left gap-2"
      >
        <div className="flex items-start gap-2 min-w-0">
          {expanded ? (
            <ChevronDown className="w-3 h-3 text-operator-muted shrink-0 mt-0.5" />
          ) : (
            <ChevronRight className="w-3 h-3 text-operator-muted shrink-0 mt-0.5" />
          )}
          <Terminal className="w-3 h-3 text-operator-muted shrink-0 mt-0.5" />
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 min-w-0">
              <span className="font-semibold text-operator-text shrink-0">{trace.toolId}</span>
              <span className={`text-[9px] uppercase tracking-wider font-semibold ${statusColor}`}>
                {trace.ok ? 'Success' : 'Error'}
              </span>
            </div>
            <div className="text-[11px] text-operator-muted/80 mt-0.5 break-words leading-relaxed">
              {hasInlineFiles ? `${readFiles.length} file${readFiles.length === 1 ? '' : 's'} read` : summary}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-1.5 pt-0.5 shrink-0">
          <span className={`${statusColor} flex items-center gap-1`}>
            <StatusIcon className="w-3 h-3" />
            <span className="text-[9px] font-semibold uppercase">{trace.ok ? 'SUCCESS' : 'ERROR'}</span>
          </span>
        </div>
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
