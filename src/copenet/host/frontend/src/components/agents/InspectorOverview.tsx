import type React from 'react';
import { FolderOpen, Info, Package, Send, Settings2, ShieldAlert } from 'lucide-react';
import { useArtifacts, useDestinations, usePendingApproval } from '../../runtime/adapter';
import { useAppStore } from '../../store/useAppStore';
import { ApprovalRequestCard } from '../ApprovalRequestCard';

function timeAgo(dateString?: string | null) {
  if (!dateString) return '--';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / (1000 * 60));
  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${Math.floor(diffHours / 24)}d ago`;
}

function Section({ icon: Icon, title, children }: { icon: typeof Info; title: string; children: React.ReactNode }) {
  return (
    <section className="border-b border-operator-border/70 pb-3 last:border-b-0">
      <div className="mb-2 flex items-center gap-1.5 text-operator-muted">
        <Icon className="h-3.5 w-3.5" />
        <h3 className="text-[10px] font-semibold uppercase tracking-wider">{title}</h3>
      </div>
      {children}
    </section>
  );
}

export function InspectorOverview({ overviewOnly = false }: { overviewOnly?: boolean }) {
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const sessions = useAppStore((state) => state.sessions);
  const messagesMap = useAppStore((state) => state.messages);
  const providers = useAppStore((state) => state.providers);
  const profiles = useAppStore((state) => state.profiles);
  const taskModes = useAppStore((state) => state.taskModes);
  const draftSettings = useAppStore((state) => state.draftSettings);
  const runtimeContext = useAppStore((state) => state.runtimeContext);
  const setAgentWorkspaceTab = useAppStore((state) => state.setAgentWorkspaceTab);
  const activeSession = sessions.find((session) => session.key === activeSessionKey) || null;
  const messages = activeSessionKey ? messagesMap[activeSessionKey] || [] : [];
  const isDraft = !activeSession;
  const pendingApproval = usePendingApproval(activeSessionKey);
  const artifactsResource = useArtifacts(isDraft ? null : activeSessionKey);
  const destinations = useDestinations();
  const currentProvider = isDraft ? draftSettings.provider : activeSession?.provider || '';
  const currentProfile = isDraft ? draftSettings.systemPromptId : activeSession?.systemPromptId || '';
  const currentTaskMode = isDraft ? draftSettings.taskPromptId : activeSession?.taskPromptId || '';
  const currentModel = isDraft ? draftSettings.model : activeSession?.model || '';
  const providerName = providers.find((provider) => provider.id === currentProvider)?.displayName || currentProvider || 'None';
  const profileName = profiles.find((profile) => profile.id === currentProfile)?.name || currentProfile || 'Default';
  const taskModeName = taskModes.find((mode) => mode.id === currentTaskMode)?.name || currentTaskMode || 'None';
  const artifacts = artifactsResource.status === 'ready' && artifactsResource.data ? artifactsResource.data : [];

  return (
    <div className={`${overviewOnly ? 'px-3 py-3' : 'px-2.5 pb-2.5'} flex flex-col gap-3 text-[12px]`}>
      {pendingApproval && <ApprovalRequestCard approval={pendingApproval} />}

      <Section icon={Settings2} title="Overview">
        <div className="space-y-1.5">
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Connection</span><span className="font-semibold text-operator-success">Connected</span></div>
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Provider</span><span className="text-right text-operator-text">{providerName}</span></div>
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Model</span><span className="text-right text-operator-text">{currentModel || '--'}</span></div>
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Profile</span><span className="text-right text-operator-text">{profileName}</span></div>
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Mode</span><span className="text-right text-operator-text">{taskModeName}</span></div>
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Session</span><span className={`font-semibold ${isDraft ? 'text-operator-accent' : 'text-operator-success'}`}>{isDraft ? 'Draft' : 'Locked'}</span></div>
          {(activeSession?.workspaceRoot || runtimeContext?.workspaceRoot) && (
            <div className="pt-1 text-[11px] leading-5 text-operator-muted break-all">{activeSession?.workspaceRoot || runtimeContext?.workspaceRoot}</div>
          )}
        </div>
      </Section>

      <Section icon={Package} title={`Artifacts${artifacts.length ? ` (${artifacts.length})` : ''}`}>
        {artifacts.length === 0 ? (
          <div className="text-[11px] text-operator-muted">No session artifacts yet.</div>
        ) : (
          <div className="space-y-2">
            {artifacts.slice(0, 3).map((artifact) => (
              <div key={artifact.id} className="rounded-xl border border-operator-border bg-operator-panel/30 px-2.5 py-2">
                <div className="truncate text-[12px] font-medium text-operator-text">{artifact.title}</div>
                <div className="mt-1 text-[10px] text-operator-muted">{artifact.oneLine}</div>
              </div>
            ))}
            <button
              type="button"
              onClick={() => setAgentWorkspaceTab('artifacts')}
              className="inline-flex items-center gap-1.5 text-[11px] font-semibold text-operator-accent transition-colors hover:text-operator-text"
            >
              <FolderOpen className="h-3 w-3" />
              View all artifacts
            </button>
          </div>
        )}
      </Section>

      <Section icon={Send} title="Messaging & Destinations">
        {destinations.length === 0 ? (
          <div className="text-[11px] text-operator-muted">No configured destinations yet.</div>
        ) : (
          <div className="space-y-2">
            {destinations.slice(0, 3).map((destination) => (
              <div key={destination.id} className="rounded-xl border border-operator-border bg-operator-panel/30 px-2.5 py-2">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 truncate text-[12px] font-medium text-operator-text">{destination.displayName}</div>
                  <span className={`text-[10px] font-semibold ${destination.requiresApproval ? 'text-operator-accent' : 'text-operator-success'}`}>
                    {destination.requiresApproval ? 'Approval required' : 'Direct send'}
                  </span>
                </div>
                <div className="mt-1 break-all text-[10px] text-operator-muted">{destination.target}</div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section icon={Info} title="Session Info">
        <div className="space-y-1.5">
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Created</span><span className="text-operator-text">{timeAgo(activeSession?.createdAt)}</span></div>
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Updated</span><span className="text-operator-text">{timeAgo(activeSession?.updatedAt)}</span></div>
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Messages</span><span className="text-operator-text">{messages.length}</span></div>
          <div className="flex justify-between gap-3"><span className="text-operator-muted">Artifacts</span><span className="text-operator-text">{artifacts.length}</span></div>
        </div>
      </Section>
    </div>
  );
}
