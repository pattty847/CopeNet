import { useState } from 'react';
import {
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  File,
  Layers,
  Package,
  Search,
  Shield,
  Sparkles,
  StickyNote,
  Terminal,
  WandSparkles,
  XCircle,
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import type {
  ActivityBundle,
  ActivityItem,
  ActivityNote,
  ActivityProofGroup,
  ActivityProofMember,
  ActivityProofGroupKind,
  ActivityReadBatch,
  ActivityToolCall,
} from '../../runtime/types';

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

function PolicyBadge({ decision }: { decision?: 'allowed' | 'read_roam' | 'write_blocked' | 'approval_required' | 'unsafe_unknown' | null }) {
  if (!decision || decision === 'allowed') return null;
  const tone =
    decision === 'write_blocked'
      ? 'border-operator-error/30 bg-operator-error/10 text-operator-error'
      : decision === 'approval_required'
        ? 'border-amber-400/30 bg-amber-400/10 text-amber-300'
        : decision === 'unsafe_unknown'
          ? 'border-fuchsia-400/30 bg-fuchsia-400/10 text-fuchsia-300'
          : 'border-sky-400/30 bg-sky-400/10 text-sky-300';
  const label =
    decision === 'write_blocked'
      ? 'write blocked'
      : decision === 'approval_required'
        ? 'approval req'
        : decision === 'unsafe_unknown'
          ? 'policy block'
          : 'read roam';
  return (
    <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] ${tone}`}>
      {label}
    </span>
  );
}

function memberStatusIcon(status: ActivityProofMember['status']) {
  if (status === 'success') return <CheckCircle2 className="h-3.5 w-3.5 text-operator-success" />;
  if (status === 'blocked') return <Shield className="h-3.5 w-3.5 text-amber-400" />;
  return <XCircle className="h-3.5 w-3.5 text-operator-error" />;
}

function groupMeta(group: ActivityProofGroupKind) {
  if (group === 'files_read') return { icon: File, tone: 'text-sky-300', chip: 'Files Read' };
  if (group === 'files_edited') return { icon: WandSparkles, tone: 'text-emerald-300', chip: 'Files Edited' };
  if (group === 'skills') return { icon: Sparkles, tone: 'text-fuchsia-300', chip: 'Skills' };
  if (group === 'artifacts') return { icon: Package, tone: 'text-operator-accent', chip: 'Artifacts' };
  return { icon: Terminal, tone: 'text-operator-accent', chip: 'Commands' };
}

function ProofMemberRow({ member, group }: { member: ActivityProofMember; group: ActivityProofGroupKind }) {
  const setInspectorTarget = useAppStore((s) => s.setInspectorTarget);
  const [expanded, setExpanded] = useState(false);
  const canExpand = !!member.fullOutput && member.fullOutput !== member.detail;
  const pathLabel = member.target ? shortPath(member.target) : shortPath(member.label);

  return (
    <div className="rounded-xl border border-operator-border/60 bg-operator-bg/50">
      <div className="flex items-start gap-2 px-3 py-2">
        <div className="mt-0.5 shrink-0">{memberStatusIcon(member.status)}</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-2">
            <div className="min-w-0 flex-1">
              <div className="truncate text-[11.5px] font-medium text-operator-text" title={member.label}>
                {group === 'files_read' || group === 'files_edited' ? pathLabel : member.label}
              </div>
              {member.toolId ? (
                <div className="mt-0.5 text-[10px] font-mono text-operator-muted/65">{member.toolId}</div>
              ) : null}
            </div>
            {member.fileCount ? (
              <span className="shrink-0 text-[10px] font-mono text-operator-muted/70">{member.fileCount} file{member.fileCount === 1 ? '' : 's'}</span>
            ) : null}
            {member.additions != null && member.deletions != null && (member.additions > 0 || member.deletions > 0) ? (
              <span className="shrink-0 text-[10px] font-mono text-operator-muted/70">+{member.additions} / -{member.deletions}</span>
            ) : null}
          </div>
          {member.detail ? <div className="mt-1 text-[10.5px] leading-snug text-operator-muted/80">{member.detail}</div> : null}
          {member.outputPreview && member.outputPreview !== member.label && member.outputPreview !== member.detail ? (
            <div className="mt-1 text-[10.5px] leading-snug text-operator-muted/65">{member.outputPreview}</div>
          ) : null}
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {member.artifactId ? (
              <button
                type="button"
                onClick={() => setInspectorTarget({ kind: 'artifact', artifactId: member.artifactId! })}
                className="text-[10px] font-semibold uppercase tracking-[0.12em] text-operator-accent transition-colors duration-150 hover:text-operator-text"
              >
                Open artifact
              </button>
            ) : null}
            {canExpand ? (
              <button
                type="button"
                onClick={() => setExpanded((value) => !value)}
                className="inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-operator-muted transition-colors duration-150 hover:text-operator-text"
              >
                {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                {expanded ? 'Hide proof' : 'Show proof'}
              </button>
            ) : null}
          </div>
          {expanded && member.fullOutput ? (
            <pre className="mt-2 overflow-x-auto rounded-lg border border-operator-border bg-operator-bg px-2.5 py-2 text-[10px] font-mono leading-[1.55] text-operator-text/75 whitespace-pre-wrap break-words">
              {member.fullOutput}
            </pre>
          ) : null}
        </div>
      </div>
    </div>
  );
}

function ProofGroupCard({ group }: { group: ActivityProofGroup }) {
  const [expanded, setExpanded] = useState(false);
  const meta = groupMeta(group.group);
  const Icon = meta.icon;

  return (
    <div className="overflow-hidden rounded-2xl border border-operator-border bg-operator-panel/35">
      <button
        type="button"
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-start gap-2.5 px-3 py-2.5 text-left transition-colors duration-150 hover:bg-operator-panel/55"
      >
        <div className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-white/[0.04] ${meta.tone}`}>
          <Icon className="h-3.5 w-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="mb-0.5 flex items-center gap-2">
            <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-operator-accent">{meta.chip}</span>
            <span className="text-[10px] font-mono text-operator-muted/65">{timeOf(group.at)}</span>
          </div>
          <div className="text-[12px] font-medium leading-snug text-operator-text">{group.label}</div>
          {group.summary ? <div className="mt-0.5 line-clamp-2 text-[10.5px] leading-snug text-operator-muted/75">{group.summary}</div> : null}
        </div>
        <div className="pt-1 text-operator-muted">{expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</div>
      </button>
      {expanded ? (
        <div className="space-y-2 border-t border-operator-border/60 bg-operator-bg/35 px-2.5 py-2.5 animate-fade-in-up">
          {group.members.map((member) => <ProofMemberRow key={member.id} member={member} group={group.group} />)}
        </div>
      ) : null}
    </div>
  );
}

function ToolCallRow({ call, compact }: { call: ActivityToolCall; compact?: boolean }) {
  const isBlocked = !call.ok && (
    call.summary?.toLowerCase().includes('blocked') ||
    call.summary?.toLowerCase().includes('policy')
  );
  const StatusIcon = call.ok ? CheckCircle2 : isBlocked ? Shield : XCircle;
  const statusColor = call.ok ? 'text-operator-success' : isBlocked ? 'text-amber-400' : 'text-operator-error';

  return (
    <div className={`flex items-start gap-1.5 text-[11px] leading-snug ${compact ? 'py-0.5' : 'py-1'}`}>
      <Terminal className="mt-0.5 h-3 w-3 shrink-0 text-operator-muted/70" />
      <span className="shrink-0 font-mono text-[10px] text-operator-text/70">{call.toolId}</span>
      {call.target ? (
        <span className="min-w-0 flex-1 truncate font-mono text-operator-accent/75" title={call.target}>
          {shortPath(call.target)}
        </span>
      ) : (
        <span className="min-w-0 flex-1 truncate text-operator-muted/80" title={call.summary}>
          {call.summary}
        </span>
      )}
      <ScopeBadge scope={call.scope} />
      <PolicyBadge decision={call.policyDecision} />
      <span className="shrink-0 font-mono text-[10px] text-operator-muted/60">{formatDuration(call.durationMs)}</span>
      <StatusIcon className={`h-3 w-3 shrink-0 ${statusColor}`} />
    </div>
  );
}

function LegacyBatchCard({ batch }: { batch: ActivityReadBatch }) {
  const [expanded, setExpanded] = useState(false);
  const setInspectorTarget = useAppStore((s) => s.setInspectorTarget);
  const okCount = batch.calls.filter((c) => c.ok).length;

  return (
    <div className="overflow-hidden rounded-xl border border-operator-border bg-operator-panel/40">
      <button onClick={() => setExpanded((v) => !v)} className="w-full px-2.5 py-2 text-left transition-colors duration-150 hover:bg-operator-panel/60">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-operator-accent/10 text-operator-accent">
            <Layers className="h-3 w-3" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-0.5 flex items-center gap-1.5">
              <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">Read Batch</span>
              <span className="font-mono text-[10px] text-operator-muted/70">{timeOf(batch.at)}</span>
            </div>
            <div className="text-[12px] font-medium leading-snug text-operator-text">{batch.label}</div>
            <div className="mt-0.5 text-[11px] text-operator-muted"><span className="font-mono">{okCount}/{batch.calls.length}</span> calls merged</div>
          </div>
          <div className="pt-1 text-operator-muted">{expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</div>
        </div>
      </button>
      {expanded ? (
        <div className="space-y-0.5 border-t border-operator-border/60 bg-operator-bg/40 px-2.5 py-1.5 animate-fade-in-up">
          {batch.calls.map((c) => <ToolCallRow key={c.id} call={c} compact />)}
          <button onClick={() => setInspectorTarget({ kind: 'batch', batchId: batch.id })} className="mt-1 text-[11px] font-medium text-operator-accent transition-colors duration-150 hover:text-operator-text">Inspect batch →</button>
        </div>
      ) : null}
    </div>
  );
}

function LegacyBundleCard({ bundle }: { bundle: ActivityBundle }) {
  const [expanded, setExpanded] = useState(false);
  const setInspectorTarget = useAppStore((s) => s.setInspectorTarget);

  return (
    <div className="overflow-hidden rounded-xl border border-operator-accent/20 bg-operator-accent/5">
      <button onClick={() => setExpanded((v) => !v)} className="w-full px-2.5 py-2 text-left transition-colors duration-150 hover:bg-operator-accent/8">
        <div className="flex items-start gap-2">
          <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-operator-accent/15 text-operator-accent">
            <Package className="h-3 w-3" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-0.5 flex items-center gap-1.5">
              <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent">Bundle</span>
              <span className="font-mono text-[10px] text-operator-muted/70">{timeOf(bundle.at)}</span>
            </div>
            <div className="text-[12px] font-medium leading-snug text-operator-text">{bundle.label}</div>
            {bundle.producedArtifactId ? (
              <div className="mt-0.5 flex items-center gap-1.5 text-[11px] text-operator-muted">
                <ArrowRight className="h-2.5 w-2.5" />
                <button onClick={(e) => { e.stopPropagation(); setInspectorTarget({ kind: 'artifact', artifactId: bundle.producedArtifactId! }); }} className="text-operator-accent transition-colors duration-150 hover:text-operator-text">produced artifact</button>
              </div>
            ) : null}
          </div>
          <div className="pt-1 text-operator-muted">{expanded ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}</div>
        </div>
      </button>
      {expanded ? <div className="space-y-0.5 border-t border-operator-accent/15 bg-operator-bg/40 px-2.5 py-1.5 animate-fade-in-up">{bundle.calls.map((c) => <ToolCallRow key={c.id} call={c} compact />)}</div> : null}
    </div>
  );
}

function SingleCallCard({ call }: { call: ActivityToolCall }) {
  const setInspectorTarget = useAppStore((s) => s.setInspectorTarget);
  return (
    <div className="flex items-start gap-2 rounded-xl border border-operator-border bg-operator-panel/30 px-2.5 py-2">
      <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-operator-panel text-operator-muted">
        <Terminal className="h-3 w-3" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="mb-0.5 flex items-center gap-1.5">
          <span className="font-mono text-[10px] text-operator-muted/70">{call.toolId}</span>
          <span className="font-mono text-[10px] text-operator-muted/50">{timeOf(call.at)}</span>
          {call.durationMs > 0 ? <span className="ml-auto font-mono text-[10px] text-operator-muted/50">{formatDuration(call.durationMs)}</span> : null}
        </div>
        {call.target ? <div className="truncate font-mono text-[11px] text-operator-accent/80" title={call.target}>{shortPath(call.target)}</div> : <div className="truncate text-[12px] leading-snug text-operator-muted/80">{call.summary}</div>}
        {call.target && call.summary && call.summary !== call.target ? <div className="mt-0.5 truncate text-[11px] leading-snug text-operator-muted/60">{call.summary}</div> : null}
        <div className="mt-1 flex items-center gap-1.5">
          <ScopeBadge scope={call.scope} />
          <PolicyBadge decision={call.policyDecision} />
          {call.artifactId ? <button type="button" onClick={() => setInspectorTarget({ kind: 'artifact', artifactId: call.artifactId! })} className="text-[10px] font-semibold uppercase tracking-[0.12em] text-operator-accent transition-colors duration-150 hover:text-operator-text">Inspect</button> : null}
        </div>
        {call.policySummary && call.policyDecision ? <div className="mt-1 text-[10.5px] leading-snug text-operator-muted/65">{call.policySummary}</div> : null}
      </div>
      {call.ok ? <CheckCircle2 className="mt-1 h-3.5 w-3.5 shrink-0 text-operator-success" /> : <XCircle className="mt-1 h-3.5 w-3.5 shrink-0 text-operator-error" />}
    </div>
  );
}

function NoteCard({ note }: { note: ActivityNote }) {
  return (
    <div className="flex items-start gap-2 rounded-xl border border-dashed border-operator-border bg-operator-panel/20 px-2.5 py-2">
      <StickyNote className="mt-0.5 h-3 w-3 shrink-0 text-operator-muted" />
      <div className="min-w-0 flex-1">
        <div className="mb-0.5 flex items-center gap-1.5">
          <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-muted">Note</span>
          <span className="font-mono text-[10px] text-operator-muted/70">{timeOf(note.at)}</span>
        </div>
        <div className="text-[11px] italic leading-relaxed text-operator-text/90">{note.text}</div>
      </div>
    </div>
  );
}

export function renderToolActivityItem(item: ActivityItem) {
  switch (item.kind) {
    case 'proof_group':
      return <ProofGroupCard key={item.id} group={item} />;
    case 'read_batch':
      return <LegacyBatchCard key={item.id} batch={item} />;
    case 'bundle':
      return <LegacyBundleCard key={item.id} bundle={item} />;
    case 'tool_call':
      return <SingleCallCard key={item.id} call={item} />;
    case 'note':
      return <NoteCard key={item.id} note={item} />;
  }
}
