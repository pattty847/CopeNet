import { useState } from 'react';
import {
  AlertTriangle,
  Brain,
  ChevronDown,
  ChevronUp,
  Code2,
  FileCode2,
  FileVideo,
  HelpCircle,
  Info,
  Link2,
  ShieldAlert,
  Sparkles,
  StickyNote,
} from 'lucide-react';
import { useWorkingSet } from '../../runtime/adapter';
import { useIsMobile } from '../../lib/responsive';
import {
  getWorkingSetSectionLabel,
  shouldCollapseWorkingSetByDefault,
  shouldUseWorkingSetCompactGrid,
} from '../../lib/agentMobile';
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

// Inline strip variants — compact because this card sits above the chat.
function InlineStrip({ icon: Icon, tone, children }: {
  icon: typeof Brain;
  tone: 'muted' | 'accent' | 'error';
  children: React.ReactNode;
}) {
  const toneCls =
    tone === 'accent'
      ? 'text-operator-accent border-operator-accent/20 bg-operator-accent/5'
      : tone === 'error'
      ? 'text-operator-error border-operator-error/25 bg-operator-error/5'
      : 'text-operator-muted border-operator-border bg-operator-panel/20';
  return (
    <div className={`mx-4 mt-3 rounded-xl border px-3 py-2 flex items-center gap-2 ${toneCls} ${tone === 'muted' ? 'border-dashed' : ''}`}>
      <Icon className="w-3.5 h-3.5 shrink-0" />
      <div className="text-[11px] leading-relaxed">{children}</div>
    </div>
  );
}

export function WorkingSetCard({ sessionKey, isDraft }: WorkingSetCardProps) {
  const isMobile = useIsMobile();
  const [expanded, setExpanded] = useState(() => !shouldCollapseWorkingSetByDefault(isMobile));
  // Drafts bypass the adapter entirely — draft is a UI state, not runtime data.
  const resource = useWorkingSet(isDraft ? null : sessionKey);

  if (isDraft) {
    return (
      <InlineStrip icon={Sparkles} tone="muted">
        Working Set will populate after the first turn — live task summary, entities, constraints, and open questions.
      </InlineStrip>
    );
  }

  if (resource.status === 'loading') {
    return (
      <div className="mx-4 mt-3 rounded-xl border border-operator-border bg-operator-panel/40 overflow-hidden">
        <div className="px-3 py-2.5 flex items-center gap-2.5">
          <div className="shimmer h-7 w-7 rounded-lg bg-operator-panel" />
          <div className="flex-1 space-y-1.5">
            <div className="shimmer h-2 w-28 rounded bg-operator-panel" />
            <div className="shimmer h-3 w-full rounded bg-operator-panel" />
          </div>
        </div>
      </div>
    );
  }

  if (resource.status === 'error') {
    return (
      <InlineStrip icon={AlertTriangle} tone="error">
        Working Set failed to load: {resource.error}
      </InlineStrip>
    );
  }

  if (resource.status === 'empty' || !resource.data) {
    return (
      <InlineStrip icon={Brain} tone="muted">
        No Working Set for this session yet. It will appear once the agent begins planning.
      </InlineStrip>
    );
  }

  const workingSet = resource.data;
  const status = STATUS_META[workingSet.status];

  return (
    <div className={`${isMobile ? 'mx-3 mt-2.5' : 'mx-4 mt-3'} rounded-xl border border-operator-border bg-operator-panel/40 overflow-hidden`}>
      <button
        onClick={() => setExpanded((v) => !v)}
        className={`w-full flex items-start gap-2.5 text-left hover:bg-operator-panel/60 transition-colors duration-150 ${
          isMobile ? 'px-3 py-2' : 'px-3 py-2.5'
        }`}
      >
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-operator-accent/10 text-operator-accent shrink-0 mt-0.5">
          <Brain className="w-3.5 h-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className={`mb-0.5 flex items-center gap-2 ${isMobile ? 'flex-wrap' : ''}`}>
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
          <div className={`${isMobile ? 'text-[12px]' : 'text-[13px]'} text-operator-text leading-snug ${expanded ? 'line-clamp-2' : 'line-clamp-1'}`}>
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
        <div className={`border-t border-operator-border/60 px-3 py-2.5 grid gap-3 animate-fade-in-up ${shouldUseWorkingSetCompactGrid(isMobile) ? 'grid-cols-3 gap-2' : 'grid-cols-1 md:grid-cols-3'}`}>
          <div>
            <div className="mb-1.5 truncate text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
              {getWorkingSetSectionLabel('entities', isMobile)} · {workingSet.entities.length}
            </div>
            <ul className="space-y-1">
              {workingSet.entities.slice(0, 5).map((e) => {
                const Icon = entityIcon(e.kind);
                return (
                  <li key={e.id} className={`flex items-start gap-1.5 leading-snug ${isMobile ? 'text-[11px]' : 'text-[12px]'}`}>
                    <Icon className="w-3 h-3 text-operator-muted mt-0.5 shrink-0" />
                    <div className="min-w-0">
                      <div className={`truncate font-mono text-operator-text ${isMobile ? 'text-[10px]' : 'text-[11px]'}`} title={e.label}>{e.label}</div>
                      {e.detail && (
                        <div className={`truncate text-operator-muted/80 ${isMobile ? 'text-[9px]' : 'text-[10px]'}`} title={e.detail}>{e.detail}</div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>

          <div>
            <div className="mb-1.5 truncate text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
              {getWorkingSetSectionLabel('constraints', isMobile)} · {workingSet.constraints.length}
            </div>
            <ul className="space-y-1">
              {workingSet.constraints.map((c) => {
                const Icon = constraintIcon(c.severity);
                const tone = constraintTone(c.severity);
                return (
                  <li key={c.id} className={`flex items-start gap-1.5 leading-snug ${isMobile ? 'text-[11px]' : 'text-[12px]'}`}>
                    <Icon className={`w-3 h-3 mt-0.5 shrink-0 ${tone}`} />
                    <span className={`text-operator-text/90 ${isMobile ? 'line-clamp-2 text-[10px]' : ''}`} title={c.text}>{c.text}</span>
                  </li>
                );
              })}
            </ul>
          </div>

          <div>
            <div className="mb-1.5 truncate text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
              {getWorkingSetSectionLabel('questions', isMobile)} · {workingSet.questions.length}
            </div>
            <ul className="space-y-1">
              {workingSet.questions.map((q) => (
                <li key={q.id} className={`flex items-start gap-1.5 leading-snug ${isMobile ? 'text-[11px]' : 'text-[12px]'}`}>
                  <HelpCircle className="w-3 h-3 text-operator-accent mt-0.5 shrink-0" />
                  <span className={`text-operator-text/90 ${isMobile ? 'line-clamp-2 text-[10px]' : ''}`} title={q.text}>{q.text}</span>
                </li>
              ))}
              {workingSet.questions.length === 0 && (
                <li className={`text-operator-muted italic ${isMobile ? 'text-[10px]' : 'text-[11px]'}`}>No open questions</li>
              )}
            </ul>
          </div>
        </div>
      )}
    </div>
  );
}
