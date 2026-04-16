import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Terminal, CheckCircle2, XCircle } from 'lucide-react';
import { ToolExecution } from '../types/backend';

export function ToolTraceCard({ trace }: { trace: ToolExecution }) {
  const [expanded, setExpanded] = useState(false);
  const statusColor = trace.ok ? 'text-operator-success' : 'text-operator-error';
  const StatusIcon = trace.ok ? CheckCircle2 : XCircle;
  const summary = trace.summary?.trim() || (trace.ok ? 'Tool completed successfully.' : 'Tool execution failed.');
  const cardTone = trace.ok ? 'border-operator-border bg-operator-bg' : 'border-operator-error/25 bg-operator-error/5';

  return (
    <div className={`border rounded-xl overflow-hidden text-[12px] shadow-sm ${cardTone}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start justify-between p-2.5 hover:bg-operator-panel transition-colors duration-150 text-left gap-2"
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
              {summary}
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
        <div className="p-2.5 border-t border-operator-border bg-operator-panel/20 overflow-x-auto">
          <div className="mb-2.5">
            <div className="text-operator-muted mb-1 text-[9px] font-semibold tracking-wider uppercase">Summary</div>
            <pre className="text-operator-text text-[11px] bg-operator-bg p-2 rounded-lg border border-operator-border whitespace-pre-wrap">
              {summary}
            </pre>
          </div>
          {trace.error && (
            <div>
              <div className="mb-1 text-[9px] font-semibold tracking-wider uppercase text-operator-error">Error</div>
              <pre className="text-[11px] bg-operator-bg p-2 rounded-lg border border-operator-error/25 text-operator-error whitespace-pre-wrap">
                {trace.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
