import { MessageSquare, Package, Workflow } from 'lucide-react';
import type { AgentWorkspaceTab } from '../../store/useAppStore';
import { useArtifacts, useRunActivity } from '../../runtime/adapter';
import { useAppStore } from '../../store/useAppStore';

const TABS: Array<{ id: AgentWorkspaceTab; label: string; icon: typeof MessageSquare }> = [
  { id: 'messages', label: 'Messages', icon: MessageSquare },
  { id: 'tool_activity', label: 'Tool Activity', icon: Workflow },
  { id: 'artifacts', label: 'Artifacts', icon: Package },
];

export function AgentWorkspaceTabs({
  value,
  onChange,
  sessionKey,
  isDraft,
}: {
  value: AgentWorkspaceTab;
  onChange: (tab: AgentWorkspaceTab) => void;
  sessionKey: string | null;
  isDraft: boolean;
}) {
  const activeRunId = useAppStore((state) => state.activeRunId);
  const artifactsRes = useArtifacts(isDraft ? null : sessionKey);
  const activityRes = useRunActivity(isDraft ? null : sessionKey);

  const artifactCount = artifactsRes.status === 'ready' && artifactsRes.data ? artifactsRes.data.length : 0;
  const activityCount = activityRes.status === 'ready' && activityRes.data ? activityRes.data.items.length : 0;

  const counts: Record<AgentWorkspaceTab, number | null> = {
    messages: null,
    tool_activity: activityCount || null,
    artifacts: artifactCount || null,
  };

  const liveOnTab: Record<AgentWorkspaceTab, boolean> = {
    messages: false,
    tool_activity: Boolean(activeRunId),
    artifacts: false,
  };

  return (
    <div className="border-b border-operator-border bg-operator-bg/60 px-3">
      <div className="-mb-px flex items-center gap-0.5 text-[11px] font-medium">
        {TABS.map((tab) => {
          const active = value === tab.id;
          const Icon = tab.icon;
          const count = counts[tab.id];
          const live = liveOnTab[tab.id];
          return (
            <button
              key={tab.id}
              type="button"
              onClick={() => onChange(tab.id)}
              className={`relative inline-flex items-center gap-1.5 border-b-2 px-2.5 py-2 transition-colors ${
                active
                  ? 'border-operator-accent text-operator-accent'
                  : 'border-transparent text-operator-muted hover:text-operator-text'
              }`}
            >
              <Icon className="h-3.5 w-3.5" />
              <span>{tab.label}</span>
              {count != null && count > 0 && (
                <span
                  className={`ml-0.5 inline-flex h-4 min-w-[1rem] items-center justify-center rounded-full px-1 text-[9.5px] font-semibold tabular-nums ${
                    active ? 'bg-operator-accent/15 text-operator-accent' : 'bg-operator-panel text-operator-muted'
                  }`}
                >
                  {count}
                </span>
              )}
              {live && (
                <span className="relative flex h-1.5 w-1.5 ml-0.5">
                  <span className="pulse-live absolute inline-flex h-full w-full rounded-full bg-operator-accent opacity-60" />
                  <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-operator-accent" />
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
