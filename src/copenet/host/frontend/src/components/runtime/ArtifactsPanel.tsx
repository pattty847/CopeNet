import {
  Box,
  Cpu,
  ExternalLink,
  FileDiff,
  FileText,
  GitCompareArrows,
  MessageSquareQuote,
  Package,
  Send,
  ShieldAlert,
  Sparkles,
  Star,
} from 'lucide-react';
import { useAppStore } from '../../store/useAppStore';
import { useArtifacts } from '../../runtime/adapter';
import type { Artifact, ArtifactKind } from '../../runtime/types';
import { ApprovalRequestCard } from '../ApprovalRequestCard';
import { OrchestrationRunCard } from '../OrchestrationRunCard';
import { OutboundMessageCard } from '../OutboundMessageCard';
import { EmptyState, ErrorState, LoadingState } from './ResourceStates';

interface ArtifactsPanelProps {
  sessionKey: string | null;
  isDraft: boolean;
}

const KIND_META: Record<
  ArtifactKind,
  { label: string; icon: typeof FileText; tone: string; bg: string }
> = {
  patch_plan: {
    label: 'Patch Plan',
    icon: FileDiff,
    tone: 'text-operator-accent',
    bg: 'bg-operator-accent/10',
  },
  summary: {
    label: 'Summary',
    icon: FileText,
    tone: 'text-operator-success',
    bg: 'bg-operator-success/10',
  },
  answer: {
    label: 'Answer',
    icon: MessageSquareQuote,
    tone: 'text-operator-text',
    bg: 'bg-operator-panel',
  },
  tool_bundle: {
    label: 'Tool Bundle',
    icon: Package,
    tone: 'text-operator-accent',
    bg: 'bg-operator-accent/8',
  },
  diff: {
    label: 'Diff',
    icon: FileDiff,
    tone: 'text-operator-accent',
    bg: 'bg-operator-accent/10',
  },
  approval_request: {
    label: 'Approval Request',
    icon: ShieldAlert,
    tone: 'text-operator-accent',
    bg: 'bg-operator-accent/10',
  },
  outbound_message: {
    label: 'Outbound Message',
    icon: Send,
    tone: 'text-operator-success',
    bg: 'bg-operator-success/10',
  },
  orchestration_run: {
    label: 'Orchestration Run',
    icon: Cpu,
    tone: 'text-operator-accent',
    bg: 'bg-operator-accent/10',
  },
};

function timeAgo(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

function ArtifactCard({ artifact }: { artifact: Artifact }) {
  const setInspectorTarget = useAppStore((s) => s.setInspectorTarget);

  // Delegate to specialized renderers for structured artifact kinds.
  if (artifact.kind === 'approval_request' && artifact.approvalData) {
    return <ApprovalRequestCard approval={artifact.approvalData} />;
  }
  if (artifact.kind === 'outbound_message' && artifact.outboundData) {
    return <OutboundMessageCard outbound={artifact.outboundData} />;
  }
  if (artifact.kind === 'orchestration_run' && artifact.orchestrationData) {
    return <OrchestrationRunCard run={artifact.orchestrationData} />;
  }

  const meta = KIND_META[artifact.kind];
  const Icon = meta.icon;

  const openInspect = () => {
    const kind = artifact.kind === 'patch_plan' || artifact.kind === 'diff' ? 'diff' : 'artifact';
    setInspectorTarget({ kind, artifactId: artifact.id });
  };

  return (
    <div className="group lift-sm rounded-xl border border-operator-border bg-operator-panel/40 overflow-hidden">
      <div className="flex items-start gap-2.5 px-3 py-2.5">
        <div className={`flex h-8 w-8 items-center justify-center rounded-lg shrink-0 ${meta.bg} ${meta.tone}`}>
          <Icon className="w-3.5 h-3.5" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className={`text-[9px] font-semibold uppercase tracking-wider ${meta.tone}`}>
              {meta.label}
            </span>
            {artifact.promoted && (
              <span className="text-[9px] font-semibold uppercase tracking-wider text-operator-accent flex items-center gap-0.5">
                <Star className="w-2.5 h-2.5 fill-current" /> Saved
              </span>
            )}
            <span className="text-[9px] text-operator-muted/70 font-mono ml-auto">
              {timeAgo(artifact.producedAt)}
            </span>
          </div>
          <div
            className="text-[13px] text-operator-text font-medium leading-snug mb-0.5 line-clamp-2 break-words"
            title={artifact.title}
          >
            {artifact.title}
          </div>
          <div className="text-[11px] text-operator-muted leading-relaxed break-words">
            {artifact.oneLine}
          </div>
          {artifact.files && artifact.files.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {artifact.files.slice(0, 3).map((f) => (
                <span
                  key={f.path}
                  className="inline-flex items-center gap-1 rounded-md bg-operator-bg border border-operator-border px-1.5 py-0.5 text-[10px] font-mono text-operator-muted"
                >
                  <span className="truncate max-w-[200px]">{f.path.split('/').pop()}</span>
                  <span className="text-operator-success">+{f.additions}</span>
                  <span className="text-operator-error">−{f.deletions}</span>
                </span>
              ))}
              {artifact.files.length > 3 && (
                <span className="text-[10px] text-operator-muted">+{artifact.files.length - 3} more</span>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="flex items-center gap-1 px-3 py-1.5 border-t border-operator-border/60 bg-operator-bg/40 opacity-80 group-hover:opacity-100 transition-opacity duration-150">
        <button
          onClick={openInspect}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium text-operator-text hover:bg-operator-panel transition-colors duration-150"
        >
          <ExternalLink className="w-3 h-3" /> Open
        </button>
        <button
          disabled
          title="Compare — coming soon"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium text-operator-muted/60 cursor-not-allowed"
        >
          <GitCompareArrows className="w-3 h-3" /> Compare
        </button>
        <button
          disabled
          title="Promote — coming soon"
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium text-operator-muted/60 cursor-not-allowed ml-auto"
        >
          <Star className="w-3 h-3" /> Promote
        </button>
      </div>
    </div>
  );
}

export function ArtifactsPanel({ sessionKey, isDraft }: ArtifactsPanelProps) {
  // Draft sessions bypass the adapter — they never produce artifacts.
  const resource = useArtifacts(isDraft ? null : sessionKey);

  if (isDraft) {
    return (
      <EmptyState
        icon={Sparkles}
        title="No artifacts yet"
        body="The agent will produce patch plans, summaries, answers, and tool bundles here as the run unfolds."
      />
    );
  }

  if (resource.status === 'loading') return <LoadingState label="Loading artifacts…" />;
  if (resource.status === 'error') {
    return <ErrorState title="Could not load artifacts" message={resource.error ?? 'Unknown error'} />;
  }
  if (resource.status === 'empty' || !resource.data) {
    return (
      <EmptyState
        icon={Box}
        title="No artifacts produced"
        body="This session has not produced any runtime artifacts. They will stream in here as the agent works."
      />
    );
  }

  const artifacts = resource.data;

  return (
    <div className="px-3 py-2.5 space-y-2">
      <div className="flex items-center justify-between mb-0.5">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-operator-muted">
          Artifacts · {artifacts.length}
        </div>
        <button
          disabled
          className="text-[10px] text-operator-muted/60 uppercase tracking-wider cursor-not-allowed"
          title="Filter — coming soon"
        >
          All kinds
        </button>
      </div>
      <div className="space-y-2 stagger-children">
        {artifacts.map((a) => (
          <ArtifactCard key={a.id} artifact={a} />
        ))}
      </div>
    </div>
  );
}
