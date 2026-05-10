import type React from 'react';
import { Brain, FolderOpen, Info, Package, Send, Settings2, ShieldAlert } from 'lucide-react';
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
  const memoryItems = useAppStore((state) => state.memoryItems);
  const lastMemoryChange = useAppStore((state) => state.lastMemoryChange);
  const sessionIdentityUsage = useAppStore((state) => state.sessionIdentityUsage);
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
  const identityUsage = activeSessionKey ? sessionIdentityUsage[activeSessionKey] || null : null;
  const relatedMemory = identityUsage
    ? memoryItems.filter((item) => identityUsage.memoryItemIds.includes(item.id)).slice(0, 3)
    : [];
  const sessionMemoryChange = lastMemoryChange && (!activeSessionKey || !lastMemoryChange.sessionKey || lastMemoryChange.sessionKey === activeSessionKey)
    ? lastMemoryChange
    : null;

  return (
    <div className={`${overviewOnly ? 'px-3 py-3' : 'px-2.5 pb-2.5'} flex flex-col gap-3 text-[12px]`}>
      {pendingApproval && <ApprovalRequestCard approval={pendingApproval} />}

      <Section icon={Settings2} title="Runtime">
        <dl className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5">
          <dt className="text-operator-muted">Status</dt>
          <dd className={`text-right font-semibold ${isDraft ? 'text-operator-accent' : 'text-operator-success'}`}>{isDraft ? 'Draft' : 'Locked'}</dd>
          <dt className="text-operator-muted">Provider</dt>
          <dd className="truncate text-right text-operator-text" title={providerName}>{providerName}</dd>
          <dt className="text-operator-muted">Model</dt>
          <dd className="truncate text-right text-operator-text" title={currentModel || '--'}>{currentModel || '--'}</dd>
          <dt className="text-operator-muted">Profile</dt>
          <dd className="truncate text-right text-operator-text" title={profileName}>{profileName}</dd>
          <dt className="text-operator-muted">Mode</dt>
          <dd className="truncate text-right text-operator-text" title={taskModeName}>{taskModeName}</dd>
        </dl>
        {(activeSession?.workspaceRoot || runtimeContext?.workspaceRoot) && (
          <div className="mt-2 rounded-lg border border-operator-border/60 bg-operator-panel/30 px-2.5 py-1.5">
            <div className="text-[9.5px] font-semibold uppercase tracking-[0.14em] text-operator-muted/75">Workspace</div>
            <div className="mt-0.5 break-all font-mono text-[10.5px] leading-5 text-operator-text/85">
              {activeSession?.workspaceRoot || runtimeContext?.workspaceRoot}
            </div>
          </div>
        )}
      </Section>

      <Section icon={Brain} title="Identity + Memory">
        {identityUsage ? (
          <div className="space-y-2">
            <div className="rounded-lg border border-operator-border bg-operator-panel/25 px-2.5 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-[11px] font-medium text-operator-text">
                  {identityUsage.profileActive ? 'Identity overlay active' : 'Memory assist active'}
                </div>
                <div className="rounded-full border border-operator-border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-operator-accent">
                  {identityUsage.memoryCount} memory
                </div>
              </div>
              <div className="mt-1 text-[10.5px] leading-5 text-operator-muted/85">
                This run used bounded identity context and only the most relevant memory items.
              </div>
              {sessionMemoryChange ? (
                <div className="mt-2 rounded-md border border-operator-accent/20 bg-operator-accent/8 px-2 py-1 text-[10px] leading-4 text-operator-text/90">
                  Memory {sessionMemoryChange.reason === 'run_extraction' ? 'captured from this run' : 'updated'}: {sessionMemoryChange.item.title}
                </div>
              ) : null}
            </div>
            {relatedMemory.length > 0 ? (
              <div className="space-y-1.5">
                {relatedMemory.map((item) => (
                  <div key={item.id} className="rounded-lg border border-operator-border bg-operator-panel/20 px-2.5 py-1.5">
                    <div className="truncate text-[11px] font-medium text-operator-text">{item.title}</div>
                    <div className="mt-0.5 line-clamp-2 text-[10px] leading-4 text-operator-muted/85">{item.summary}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[11px] text-operator-muted/85 italic">No specific memory items were attached to the latest run.</div>
            )}
          </div>
        ) : (
          <div className="text-[11px] text-operator-muted/85 italic">Identity stays available in the background. Relevant memory appears here after a run uses it.</div>
        )}
      </Section>

      <Section icon={Package} title={`Artifacts${artifacts.length ? ` · ${artifacts.length}` : ''}`}>
        {artifacts.length === 0 ? (
          <div className="text-[11px] text-operator-muted/85 italic">No session artifacts yet.</div>
        ) : (
          <div className="space-y-1.5">
            {artifacts.slice(0, 3).map((artifact) => (
              <button
                key={artifact.id}
                type="button"
                onClick={() => setAgentWorkspaceTab('artifacts')}
                className="w-full text-left rounded-lg border border-operator-border bg-operator-panel/25 px-2.5 py-1.5 transition-colors hover:border-operator-accent/30 hover:bg-operator-panel/55"
              >
                <div className="truncate text-[12px] font-medium text-operator-text">{artifact.title}</div>
                <div className="mt-0.5 truncate text-[10.5px] text-operator-muted/85">{artifact.oneLine}</div>
              </button>
            ))}
            {artifacts.length > 3 && (
              <button
                type="button"
                onClick={() => setAgentWorkspaceTab('artifacts')}
                className="inline-flex items-center gap-1.5 pt-0.5 text-[11px] font-semibold text-operator-accent transition-colors hover:text-operator-text"
              >
                <FolderOpen className="h-3 w-3" />
                View all {artifacts.length} artifacts
              </button>
            )}
          </div>
        )}
      </Section>

      <Section icon={Send} title="Destinations">
        {destinations.length === 0 ? (
          <div className="text-[11px] text-operator-muted/85 italic">No configured destinations yet.</div>
        ) : (
          <div className="space-y-1.5">
            {destinations.slice(0, 3).map((destination) => (
              <div key={destination.id} className="rounded-lg border border-operator-border bg-operator-panel/25 px-2.5 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 truncate text-[12px] font-medium text-operator-text">{destination.displayName}</div>
                  <span className={`shrink-0 rounded-full border px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] ${destination.requiresApproval ? 'border-operator-accent/25 text-operator-accent' : 'border-operator-success/25 text-operator-success'}`}>
                    {destination.requiresApproval ? 'Approval' : 'Direct'}
                  </span>
                </div>
                <div className="mt-0.5 truncate font-mono text-[10px] text-operator-muted/85">{destination.target}</div>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section icon={Info} title="Session Info">
        <dl className="grid grid-cols-[6.5rem_minmax(0,1fr)] gap-x-3 gap-y-1.5">
          <dt className="text-operator-muted">Created</dt>
          <dd className="text-right text-operator-text tabular-nums">{timeAgo(activeSession?.createdAt)}</dd>
          <dt className="text-operator-muted">Updated</dt>
          <dd className="text-right text-operator-text tabular-nums">{timeAgo(activeSession?.updatedAt)}</dd>
          <dt className="text-operator-muted">Messages</dt>
          <dd className="text-right text-operator-text tabular-nums">{messages.length}</dd>
          <dt className="text-operator-muted">Artifacts</dt>
          <dd className="text-right text-operator-text tabular-nums">{artifacts.length}</dd>
        </dl>
      </Section>
    </div>
  );
}
