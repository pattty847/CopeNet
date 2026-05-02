import { useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Layers,
  Package,
  Shield,
  Sparkles,
  StickyNote,
  Terminal,
  XCircle,
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { useLastTurnState, useRunActivity } from '../../runtime/adapter';
import type {
  ActivityBundle,
  ActivityItem,
  ActivityNote,
  ActivityReadBatch,
  ActivityToolCall,
} from '../../runtime/types';
import { EmptyState, ErrorState, LoadingState } from './ResourceStates';
import { TurnSummaryStrip } from './LiveToolFeed';

interface RunActivityPanelProps {
  sessionKey: string | null;
  isDraft: boolean;
}

function timeOf(iso: string) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function formatDuration(ms: number) {
  if (ms < 1) return '0ms';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

/** Show last 2 path segments for compact display */
function shortPath(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  if (parts.length <= 2) return path;
  return `…/${parts.slice(-2).join('/')}`;
}

function ScopeBadge({ scope }: { scope?: 'inside_workspace' | 'outside_workspace' | null }) {
  if (!scope) return null;
  const tone =
    scope === 'outside_workspace'
      ? 'border-amber-400/30 bg-amber-400/10 text-amber-300'
      : 'border-operator-border bg-operator-panel/40 text-operator-muted';
  const label = scope === 'outside_workspace' ? 'outside home' : 'inside home';
  return (
    <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] ${tone}`}>
      {label}
    </span>
  );
}

function ToolCallRow({ call, compact }: { call: ActivityToolCall; compact?: boolean }) {
  // Detect blocked state: ok=false + summary mentions 'blocked' or 'policy'
  const isBlocked = !call.ok && (
    call.summary?.toLowerCase().includes('blocked') ||
    call.summary?.toLowerCase().includes('policy')
  );
  const StatusIcon = call.ok ? CheckCircle2 : isBlocked ? Shield : XCircle;
  const statusColor = call.ok
    ? 'text-operator-success'
    : isBlocked
      ? 'text-amber-400'
      : 'text-operator-error';

  return (
    <div className={`flex items-start gap-1.5 text-[11px] leading-snug ${compact ? 'py-0.5' : 'py-1'}`}>
      <Terminal className="w-3 h-3 text-operator-muted/70 shrink-0 mt-0.5" />
      <span className="font-mono text-operator-text/70 shrink-0 text-[10px]">{call.toolId}</span>
      {call.target ? (
        <span className="font-mono text-operator-accent/75 truncate flex-1 min-w-0" title={call.target}>
          {shortPath(call.target)}
        </span>
      ) : (
          <span className="text-operator-muted/80 truncate flex-1 min-w-0" title={call.summary}>
            {call.summary}
          </span>
      )}
      <ScopeBadge scope={call.scope} />
      <span className="text-operator-muted/60 font-mono text-[10px] shrink-0">
        {formatDuration(call.durationMs)}
      </span>
      <StatusIcon className={`w-3 h-3 shrink-0 ${statusColor}`} />
    </div>
  );
}

function BatchCard({ batch }: { batch: ActivityReadBatch }) {
  const [expanded, setExpanded] = useState(false);
  const setInspectorTarget = useAppStore((s) => s.setInspectorTarget);
  const okCount = batch.calls.filter((c) => c.ok).length;

  return (
    <div className="rounded-xl border border-operator-border bg-operator-panel/40 overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2 px-2.5 py-2 hover:bg-operator-panel/60 transition-colors duration-150 text-left"
      >
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-operator-accent/10 text-operator-accent shrink-0 mt-0.5">
          <Layers className="w-3 h-3" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">
              Read Batch
            </span>
            <span className="text-[10px] font-mono text-operator-muted/70">{timeOf(batch.at)}</span>
          </div>
          <div className="text-[12px] text-operator-text font-medium leading-snug">
            {batch.label}
          </div>
          <div className="text-[11px] text-operator-muted mt-0.5">
            <span className="font-mono">{okCount}/{batch.calls.length}</span> calls merged
            {batch.mergedSummary && <span> · {batch.mergedSummary}</span>}
          </div>
        </div>
        <div className="shrink-0 pt-1 text-operator-muted">
          {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-operator-border/60 bg-operator-bg/40 px-2.5 py-1.5 space-y-0.5 animate-fade-in-up">
          {batch.calls.map((c) => (
            <ToolCallRow key={c.id} call={c} compact />
          ))}
          <button
            onClick={() => setInspectorTarget({ kind: 'batch', batchId: batch.id })}
            className="mt-1 text-[11px] text-operator-accent hover:text-operator-text transition-colors duration-150 font-medium"
          >
            Inspect batch →
          </button>
        </div>
      )}
    </div>
  );
}

function BundleCard({ bundle }: { bundle: ActivityBundle }) {
  const [expanded, setExpanded] = useState(false);
  const setInspectorTarget = useAppStore((s) => s.setInspectorTarget);

  return (
    <div className="rounded-xl border border-operator-accent/20 bg-operator-accent/5 overflow-hidden">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2 px-2.5 py-2 hover:bg-operator-accent/8 transition-colors duration-150 text-left"
      >
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-operator-accent/15 text-operator-accent shrink-0 mt-0.5">
          <Package className="w-3 h-3" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">
              Bundle
            </span>
            <span className="text-[10px] font-mono text-operator-muted/70">{timeOf(bundle.at)}</span>
          </div>
          <div className="text-[12px] text-operator-text font-medium leading-snug">
            {bundle.label}
          </div>
          <div className="text-[11px] text-operator-muted mt-0.5 flex items-center gap-1.5">
            <span className="font-mono">{bundle.calls.length}</span> calls
            {bundle.producedArtifactId && (
              <>
                <ArrowRight className="w-2.5 h-2.5" />
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setInspectorTarget({ kind: 'artifact', artifactId: bundle.producedArtifactId! });
                  }}
                  className="text-operator-accent hover:text-operator-text transition-colors duration-150"
                >
                  produced artifact
                </button>
              </>
            )}
          </div>
        </div>
        <div className="shrink-0 pt-1 text-operator-muted">
          {expanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-operator-accent/15 bg-operator-bg/40 px-2.5 py-1.5 space-y-0.5 animate-fade-in-up">
          {bundle.calls.map((c) => (
            <ToolCallRow key={c.id} call={c} compact />
          ))}
        </div>
      )}
    </div>
  );
}

function SingleCallCard({ call }: { call: ActivityToolCall }) {
  const setInspectorTarget = useAppStore((s) => s.setInspectorTarget);
  return (
    <div className="rounded-xl border border-operator-border bg-operator-panel/30 px-2.5 py-2 flex items-start gap-2">
      <div className="flex h-6 w-6 items-center justify-center rounded-md bg-operator-panel text-operator-muted shrink-0 mt-0.5">
        <Terminal className="w-3 h-3" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="font-mono text-[10px] text-operator-muted/70">{call.toolId}</span>
          <span className="text-[10px] font-mono text-operator-muted/50">{timeOf(call.at)}</span>
          {call.durationMs > 0 && (
            <span className="text-[10px] font-mono text-operator-muted/50 ml-auto">
              {formatDuration(call.durationMs)}
            </span>
          )}
        </div>
        {call.target ? (
          <div className="font-mono text-[11px] text-operator-accent/80 truncate" title={call.target}>
            {shortPath(call.target)}
          </div>
        ) : (
          <div className="text-[12px] text-operator-muted/80 leading-snug truncate">{call.summary}</div>
        )}
        {call.target && call.summary && call.summary !== call.target && (
          <div className="text-[11px] text-operator-muted/60 leading-snug mt-0.5 truncate">{call.summary}</div>
        )}
        <div className="mt-1 flex items-center gap-1.5">
          <ScopeBadge scope={call.scope} />
          {call.artifactId && (
            <button
              type="button"
              onClick={() => setInspectorTarget({ kind: 'artifact', artifactId: call.artifactId! })}
              className="text-[10px] font-semibold uppercase tracking-[0.12em] text-operator-accent transition-colors duration-150 hover:text-operator-text"
            >
              Inspect
            </button>
          )}
        </div>
      </div>
      {call.ok ? (
        <CheckCircle2 className="w-3.5 h-3.5 text-operator-success shrink-0 mt-1" />
      ) : (
        <XCircle className="w-3.5 h-3.5 text-operator-error shrink-0 mt-1" />
      )}
    </div>
  );
}

function NoteCard({ note }: { note: ActivityNote }) {
  return (
    <div className="rounded-xl border border-dashed border-operator-border bg-operator-panel/20 px-2.5 py-2 flex items-start gap-2">
      <StickyNote className="w-3 h-3 text-operator-muted shrink-0 mt-0.5" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 mb-0.5">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted">Note</span>
          <span className="text-[10px] font-mono text-operator-muted/70">{timeOf(note.at)}</span>
        </div>
        <div className="text-[11px] text-operator-text/90 leading-relaxed italic">
          {note.text}
        </div>
      </div>
    </div>
  );
}

function renderItem(item: ActivityItem) {
  switch (item.kind) {
    case 'read_batch':
      return <BatchCard key={item.id} batch={item} />;
    case 'bundle':
      return <BundleCard key={item.id} bundle={item} />;
    case 'tool_call':
      return <SingleCallCard key={item.id} call={item} />;
    case 'note':
      return <NoteCard key={item.id} note={item} />;
  }
}

export function RunActivityPanel({ sessionKey, isDraft }: RunActivityPanelProps) {
  const resource = useRunActivity(isDraft ? null : sessionKey);
  const turnState = useLastTurnState();

  if (isDraft) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No run activity yet"
        body="Read batches, bundles, and single tool calls will appear here grouped by what the agent actually did."
      />
    );
  }

  if (resource.status === 'loading') return <LoadingState label="Loading run activity…" />;
  if (resource.status === 'error') {
    return <ErrorState title="Could not load run activity" message={resource.error ?? 'Unknown error'} />;
  }
  if (resource.status === 'empty' || !resource.data) {
    return (
      <EmptyState
        icon={Clock}
        title="No activity recorded"
        body="This session has not produced any tool activity yet. It will stream in here in real time."
      />
    );
  }

  const activity = resource.data;

  return (
    <div className="px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between mb-0.5">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
          Run Activity
        </div>
        <span className="text-[10px] text-operator-muted/70 font-mono">{activity.runId}</span>
      </div>

      <div className="relative pl-3 space-y-2 stagger-children">
        <div className="absolute left-[5px] top-1 bottom-1 w-px bg-operator-border" />
        {activity.items.map((item) => (
          <div key={item.id} className="relative">
            <span className="absolute -left-[9px] top-3 h-1.5 w-1.5 rounded-full bg-operator-accent" />
            {renderItem(item)}
          </div>
        ))}
      </div>

      {/* Turn state summary — shown when we have a completed turn snapshot */}
      {turnState && turnState.toolCallCount > 0 && (
        <div className="border-t border-operator-border/40 pt-2 mt-1">
          <TurnSummaryStrip
            callCount={turnState.toolCallCount}
            failedCount={turnState.failedActions.length}
          />
          {turnState.terminalReason && turnState.terminalReason !== 'completed' && (
            <div className="text-[10px] text-operator-muted font-mono mt-1">
              terminal: {turnState.terminalReason}
            </div>
          )}
          {turnState.openQuestions.length > 0 && (
            <div className="mt-1.5 space-y-0.5">
              {turnState.openQuestions.map((q, i) => (
                <div key={i} className="text-[10px] text-amber-400/80 italic">
                  ? {q}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
