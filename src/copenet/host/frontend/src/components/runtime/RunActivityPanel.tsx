/**
 * RunActivityPanel — the live→history collapse seam.
 *
 * While a run is active, LiveToolFeed streams per-tool chips. When the run
 * finishes, this panel takes over: the run's tool steps are synthesized (by
 * activityProof.ts::mapRunToActivity) into grouped historical breadcrumbs —
 * "Read 4 files", "Edited 2 files", "Ran 1 command", "Produced 1 artifact" —
 * one line each, collapsed by default so a vibe-coder isn't overwhelmed, each
 * expandable to inspect exactly what happened. The run's output summary lands
 * as a closing note.
 *
 * Fully real: useRunActivity reads listSessionRuns; no mock dependency.
 */

import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  FileText,
  SquarePen,
  Terminal,
  Sparkles,
  Package,
  History,
  Shield,
  XCircle,
} from 'lucide-react';
import type {
  ActivityItem,
  ActivityProofGroup,
  ActivityProofGroupKind,
  ActivityProofMember,
} from '../../runtime/types';
import { useRunActivity } from '../../runtime/adapter';
import { useAppStore } from '../../store/useAppStore';
import { ToolCallDetail } from './ToolCallDetail';

const GROUP_ICON: Record<ActivityProofGroupKind, typeof FileText> = {
  commands: Terminal,
  files_read: FileText,
  files_edited: SquarePen,
  skills: Sparkles,
  artifacts: Package,
};

function relativeTime(iso?: string | null): string {
  if (!iso) return '';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const secs = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (secs < 45) return 'just now';
  const mins = Math.round(secs / 60);
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function shortTarget(text: string): string {
  const parts = text.split('/');
  return parts.length > 3 ? `…/${parts.slice(-2).join('/')}` : text;
}

function MemberStatusIcon({ status }: { status: ActivityProofMember['status'] }) {
  if (status === 'failed') return <XCircle className="h-2.5 w-2.5 shrink-0 text-operator-error" />;
  if (status === 'blocked') return <Shield className="h-2.5 w-2.5 shrink-0 text-amber-400" />;
  return <span className="inline-block h-1 w-1 shrink-0 rounded-full bg-operator-muted/45" />;
}

function ProofMemberRow({ member }: { member: ActivityProofMember }) {
  const [expanded, setExpanded] = useState(false);
  const label = member.target ? shortTarget(member.target) : member.label;
  const hasDiffStats = member.additions != null || member.deletions != null;
  // Every call expands now, not just the ones that produced an artifact — the
  // arguments and result body are on the run record for all of them. The artifact
  // link moved inside ToolCallDetail so it is still one click away.
  return (
    <div>
      <div
        className="flex cursor-pointer items-center gap-1.5 rounded px-2 py-0.5 hover:bg-operator-panel/25"
        onClick={() => setExpanded((v) => !v)}
      >
        <MemberStatusIcon status={member.status} />
        <span className="min-w-0 flex-1 truncate font-mono text-[10.5px] text-operator-text/70" title={member.detail || member.label}>
          {label}
        </span>
        {hasDiffStats && (
          <span className="shrink-0 font-mono text-[10px] tabular-nums">
            {member.additions ? <span className="text-operator-success/80">+{member.additions}</span> : null}
            {member.deletions ? <span className="text-operator-error/80"> -{member.deletions}</span> : null}
          </span>
        )}
        {expanded ? (
          <ChevronDown className="h-2.5 w-2.5 shrink-0 text-operator-muted/35" />
        ) : (
          <ChevronRight className="h-2.5 w-2.5 shrink-0 text-operator-muted/35" />
        )}
      </div>
      {expanded && <ToolCallDetail member={member} />}
    </div>
  );
}

function ProofGroupRow({ group }: { group: ActivityProofGroup }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = GROUP_ICON[group.group] || FileText;
  const failed = group.members.filter((m) => m.status === 'failed').length;
  const blocked = group.members.filter((m) => m.status === 'blocked').length;
  return (
    <div className="overflow-hidden">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left transition-colors duration-100 hover:bg-operator-panel/25"
      >
        <Icon className="h-3 w-3 shrink-0 text-operator-muted/70" />
        <span className="text-[11px] text-operator-text/85">{group.label}</span>
        {failed > 0 && <span className="text-[10px] text-operator-error">· {failed} failed</span>}
        {blocked > 0 && <span className="text-[10px] text-amber-400">· {blocked} blocked</span>}
        <span className="ml-auto shrink-0">
          {expanded ? (
            <ChevronDown className="h-3 w-3 text-operator-muted/45" />
          ) : (
            <ChevronRight className="h-3 w-3 text-operator-muted/45" />
          )}
        </span>
      </button>
      {expanded && (
        <div className="mt-0.5 ml-1.5 border-l border-operator-border/40 pl-1.5 pb-1">
          {group.members.map((member) => (
            <ProofMemberRow key={member.id} member={member} />
          ))}
        </div>
      )}
    </div>
  );
}

function ActivityRow({ item }: { item: ActivityItem }) {
  if (item.kind === 'proof_group') return <ProofGroupRow group={item} />;
  if (item.kind === 'note') {
    return (
      <div className="rounded border-l-2 border-operator-accent/25 bg-operator-panel/15 px-2 py-1 text-[11px] leading-relaxed text-operator-muted/85">
        {item.text}
      </div>
    );
  }
  // tool_call / read_batch / bundle — mapper rarely emits these standalone, but
  // render a minimal row so nothing silently disappears.
  const label = 'label' in item ? item.label : 'toolId' in item ? item.toolId : 'activity';
  return (
    <div className="flex items-center gap-1.5 px-1.5 py-1 text-[11px] text-operator-text/75">
      <span className="inline-block h-1 w-1 shrink-0 rounded-full bg-operator-muted/45" />
      <span className="truncate">{label}</span>
    </div>
  );
}

export function RunActivityPanel({ sessionKey }: { sessionKey: string | null }) {
  const activeRunId = useAppStore((s) => sessionKey ? s.activeRunsBySession[sessionKey] || null : null);
  const activity = useRunActivity(sessionKey);

  // Hand-off: while a run is live, LiveToolFeed owns the space. This panel is
  // the post-run historical view.
  if (activeRunId) return null;
  if (activity.status !== 'ready' || !activity.data || activity.data.items.length === 0) return null;

  const run = activity.data;
  return (
    <section className="border-b border-operator-border/70 pb-3 last:border-b-0">
      <div className="mb-2 flex items-center gap-1.5 text-operator-muted">
        <History className="h-3.5 w-3.5" />
        <h3 className="text-[10px] font-semibold uppercase tracking-wider">Last run</h3>
        <span className="ml-auto font-mono text-[10px] text-operator-muted/55">
          {relativeTime(run.endedAt || run.startedAt)}
        </span>
      </div>
      <div className="space-y-0.5">
        {run.items.map((item) => (
          <ActivityRow key={item.id} item={item} />
        ))}
      </div>
    </section>
  );
}
