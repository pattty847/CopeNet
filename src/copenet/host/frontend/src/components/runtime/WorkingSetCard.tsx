import { useMemo, useState } from 'react';
import {
  Brain,
  ChevronDown,
  ChevronUp,
  FileCode2,
  Code2,
  Link2,
  FileVideo,
  StickyNote,
  AlertTriangle,
  ShieldAlert,
  Info,
  HelpCircle,
  Sparkles,
} from 'lucide-react';
import { getWorkingSet } from '../../runtime/mocks';
import type { RuntimeStatus, WorkingSetEntity } from '../../runtime/types';

interface WorkingSetCardProps {
  sessionKey: string | null;
  isDraft: boolean;
}

const STATUS_META: Record<RuntimeStatus, { label: string; dot: string; text: string }> = {
  thinking: { label: 'Thinking', dot: 'bg-operator-accent', text: 'text-operator-accent' },
  executing: { label: 'Executing', dot: 'bg-operator-success', text: 'text-operator-success' },
  awaiting_input: { label: 'Awaiting input', dot: 'bg-operator-accent', text: 'text-operator-accent' },
  idle: { label: 'Idle', dot: 'bg-operator-muted', text: 'text-operator-muted' },
};

function entityIcon(kind: WorkingSetEntity['kind']) {
  switch (kind) {
    case 'file':
      return FileCode2;
    case 'symbol':
      return Code2;
    case 'url':
      return Link2;
    case 'asset':
      return FileVideo;
    case 'note':
    default:
      return StickyNote;
  }
}

function constraintIcon(severity: 'info' | 'warn' | 'block' | undefined) {
  if (severity === 'block') return ShieldAlert;
  if (severity === 'warn') return AlertTriangle;
  return Info;
}

function constraintTone(severity: 'info' | 'warn' | 'block' | undefined) {
  if (severity === 'block') return 'text-operator-error';
  if (severity === 'warn') return 'text-operator-accent';
  return 'text-operator-muted';
}

function freshness(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const s = Math.floor(diff / 1000);
  if (s < 5) return 'just now';
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

export function WorkingSetCard({ sessionKey, isDraft }: WorkingSetCardProps) {
  const [expanded, setExpanded] = useState(true);
  const workingSet = useMemo(() => getWorkingSet(sessionKey), [sessionKey]);
  const status = STATUS_META[workingSet.status];

  // Draft sessions don't have a working set yet — show a slim placeholder so
  // the shell is visible but not noisy.
  if (isDraft) {
    return (
      <div className="mx-4 mt-3 rounded-xl border border-dashed border-operator-border bg-operator-panel/20 px-3 py-2 flex items-center gap-2">
        <Sparkles className="w-3.5 h-3.5 text-operator-muted shrink-0" />
        <span className="text-[11px] text-operator-muted leading-relaxed">
          Working Set will populate after the first turn — live task summary, entities, constraints, and open questions.
        </span>
      </div>
    );
  }

  return (
    <div className="mx-4 mt-3 rounded-xl border border-operator-border bg-operator-panel/40 overflow-hidden">
      {/* Header row — always visible */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-start gap-2.5 px-3 py-2.5 text-left hover:bg-operator-panel/60 transition-colors duration-150"
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-operator-accent/10 text-operator-accent shrink-0 mt-0.5">
          <Brain className="w-3.5 h-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">Working Set</span>
            <span className={`flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider ${status.text}`}>
              <span className="relative flex h-1.5 w-1.5">
                <span className={`pulse-live absolute inline-flex h-full w-full rounded-full ${status.dot} opacity-60`} />
                <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${status.dot}`} />
              </span>
              {status.label}
            </span>
            <span className="text-[10px] text-operator-muted/70 font-mono">{freshness(workingSet.updatedAt)}</span>
          </div>
          <div className="text-[13px] text-operator-text leading-snug line-clamp-2">
            {workingSet.taskSummary}
          </div>
        </div>
        <div className="shrink-0 pt-1">
          {expanded ? (
            <ChevronUp className="w-3.5 h-3.5 text-operator-muted" />
          ) : (
            <ChevronDown className="w-3.5 h-3.5 text-operator-muted" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-operator-border/60 px-3 py-2.5 grid grid-cols-1 md:grid-cols-3 gap-3 animate-fade-in-up">
          {/* Active entities */}
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5">
              Active Entities · {workingSet.entities.length}
            </div>
            <ul className="space-y-1">
              {workingSet.entities.slice(0, 5).map((e) => {
                const Icon = entityIcon(e.kind);
                return (
                  <li key={e.id} className="flex items-start gap-1.5 text-[12px] leading-snug">
                    <Icon className="w-3 h-3 text-operator-muted mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <div className="text-operator-text truncate font-mono text-[11px]">{e.label}</div>
                      {e.detail && (
                        <div className="text-operator-muted/80 text-[10px] truncate">{e.detail}</div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Constraints */}
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5">
              Constraints · {workingSet.constraints.length}
            </div>
            <ul className="space-y-1">
              {workingSet.constraints.map((c) => {
                const Icon = constraintIcon(c.severity);
                const tone = constraintTone(c.severity);
                return (
                  <li key={c.id} className="flex items-start gap-1.5 text-[12px] leading-snug">
                    <Icon className={`w-3 h-3 mt-0.5 shrink-0 ${tone}`} />
                    <span className="text-operator-text/90">{c.text}</span>
                  </li>
                );
              })}
            </ul>
          </div>

          {/* Open questions */}
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted mb-1.5">
              Open Questions · {workingSet.questions.length}
            </div>
            <ul className="space-y-1">
              {workingSet.questions.map((q) => (
                <li key={q.id} className="flex items-start gap-1.5 text-[12px] leading-snug">
                  <HelpCircle className="w-3 h-3 text-operator-accent mt-0.5 shrink-0" />
                  <span className="text-operator-text/90">{q.text}</span>
                </li>
              ))}
              {workingSet.questions.length === 0 && (
                <li className="text-[11px] text-operator-muted italic">No open questions</li>
              )}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
