import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Terminal, CheckCircle2, XCircle } from 'lucide-react';
import { ToolExecution } from '../types/backend';

export function ToolTraceCard({ trace }: { trace: ToolExecution }) {
  const [expanded, setExpanded] = useState(false);
  const statusColor = trace.ok ? 'text-operator-success' : 'text-operator-error';
  const StatusIcon = trace.ok ? CheckCircle2 : XCircle;
  const summary = trace.summary?.trim() || (trace.ok ? 'Tool completed successfully.' : 'Tool execution failed.');
  const cardTone = trace.ok ? 'border-operator-border bg-operator-bg' : 'border-operator-error/30 bg-operator-error/5';

  return (
    <div className={`border rounded-md overflow-hidden font-mono text-xs mt-3 shadow-sm ${cardTone}`}>
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-start justify-between p-2.5 hover:bg-operator-panel transition-colors text-left gap-3"
      >
        <div className="flex items-start gap-3 min-w-0">
          {expanded ? (
            <ChevronDown className="w-3.5 h-3.5 text-operator-muted shrink-0 mt-0.5" />
          ) : (
            <ChevronRight className="w-3.5 h-3.5 text-operator-muted shrink-0 mt-0.5" />
          )}
          <Terminal className="w-3.5 h-3.5 text-operator-muted shrink-0 mt-0.5" />
          <div className="min-w-0">
            <div className="flex items-center gap-2 min-w-0">
              <span className="font-bold text-operator-text shrink-0">{trace.toolId}</span>
              <span className={`text-[10px] uppercase tracking-wider ${statusColor}`}>
                {trace.ok ? 'Success' : 'Error'}
              </span>
            </div>
            <div className="text-operator-muted/85 mt-1 break-words leading-relaxed">
              {summary}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 pt-0.5 shrink-0">
          <span className={`${statusColor} flex items-center gap-1.5`}>
            <StatusIcon className="w-3.5 h-3.5" />
            {trace.ok ? 'SUCCESS' : 'ERROR'}
          </span>
        </div>
      </button>

      {expanded && (
        <div className="p-3 border-t border-operator-border bg-operator-panel/30 overflow-x-auto">
          <div className="mb-3">
            <div className="text-operator-muted mb-1.5 text-[10px] font-bold tracking-wider">SUMMARY</div>
            <pre className="text-operator-text text-[11px] bg-operator-bg p-2 rounded border border-operator-border whitespace-pre-wrap">
              {summary}
            </pre>
          </div>
          {trace.error && (
            <div>
              <div className="mb-1.5 text-[10px] font-bold tracking-wider text-operator-error">ERROR</div>
              <pre className="text-[11px] bg-operator-bg p-2 rounded border border-operator-error/30 text-operator-error whitespace-pre-wrap">
                {trace.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
