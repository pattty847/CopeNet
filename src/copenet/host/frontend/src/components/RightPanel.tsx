import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { DraftSettings } from '../types/backend';
import { Activity, Info, Inbox, Settings2, ChevronLeft, ChevronRight, Package, Layers, ShieldAlert } from 'lucide-react';
import { ArtifactsPanel } from './runtime/ArtifactsPanel';
import { RunActivityPanel } from './runtime/RunActivityPanel';
import { LiveToolFeed } from './runtime/LiveToolFeed';
import { ApprovalRequestCard } from './ApprovalRequestCard';
import { ApprovalQueuePanel } from './ApprovalQueuePanel';
import { OperatorActionCenter } from './OperatorActionCenter';
import { ProviderAuthCard } from './ProviderAuthCard';
import { RunTimeline } from './RunTimeline';
import { SendMessageComposer } from './SendMessageComposer';
import { usePendingApproval, useApprovalHistory, useInboxItems } from '../runtime/adapter';
import type { RightPanelTab } from '../store/useAppStore';

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
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

const selectClass =
  'bg-operator-bg border border-operator-border text-operator-text text-[12px] px-2 py-1.5 rounded-lg focus:outline-none focus:border-operator-accent/40 w-full transition-colors duration-150';

export function RightPanel({ mobile = false }: { mobile?: boolean }) {
  const panelRef = useRef<HTMLDivElement | null>(null);
  const activeSessionKey = useAppStore((state) => state.activeSessionKey);
  const sessions = useAppStore((state) => state.sessions);
  const messagesMap = useAppStore((state) => state.messages);
  const providers = useAppStore((state) => state.providers);
  const modelsByProvider = useAppStore((state) => state.modelsByProvider);
  const loadedModelProviders = useAppStore((state) => state.loadedModelProviders);
  const profiles = useAppStore((state) => state.profiles);
  const taskModes = useAppStore((state) => state.taskModes);
  const wsStatus = useAppStore((state) => state.wsStatus);
  const draftSettings = useAppStore((state) => state.draftSettings);
  const patchDraftSettings = useAppStore((state) => state.patchDraftSettings);
  const rightPanelOpen = useAppStore((state) => state.rightPanelOpen);
  const setRightPanelOpen = useAppStore((state) => state.setRightPanelOpen);
  const rightPanelTab = useAppStore((state) => state.rightPanelTab);
  const setRightPanelTab = useAppStore((state) => state.setRightPanelTab);
  const activeRunId = useAppStore((state) => state.activeRunId);

  const pendingApproval = usePendingApproval(activeSessionKey);
  const approvalHistory = useApprovalHistory(activeSessionKey);
  const pendingCount = approvalHistory.filter((r) => r.status === 'pending').length;
  const inboxItems = useInboxItems(activeSessionKey);
  const urgentCount = inboxItems.filter((i) => i.priority === 'urgent' || i.priority === 'attention').length;

  const activeSession = sessions.find((session) => session.key === activeSessionKey) || null;
  const messages = activeSessionKey ? messagesMap[activeSessionKey] || [] : [];
  const isDraft = !activeSession;

  const currentProvider = isDraft ? draftSettings.provider : activeSession.provider;
  const currentModel = isDraft ? draftSettings.model : activeSession.model || '';
  const currentProfile = isDraft ? draftSettings.systemPromptId : activeSession.systemPromptId || '';
  const currentTaskMode = isDraft ? draftSettings.taskPromptId : activeSession.taskPromptId || '';
  const availableModels = currentProvider ? modelsByProvider[currentProvider] || [] : [];
  const providerHasModels = currentProvider ? loadedModelProviders[currentProvider] : false;
  const [panelWidth, setPanelWidth] = useState(0);

  let latestTool = null;
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.toolExecution) {
      latestTool = message.toolExecution;
      break;
    }
  }

  React.useEffect(() => {
    if (!isDraft || !currentProvider || loadedModelProviders[currentProvider]) return;
    void wsClient.loadModels(currentProvider);
  }, [currentProvider, isDraft, loadedModelProviders]);

  useEffect(() => {
    const node = panelRef.current;
    if (!node || typeof ResizeObserver === 'undefined') return;
    const sync = () => setPanelWidth(node.clientWidth);
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const providerName = providers.find((provider) => provider.id === currentProvider)?.displayName || currentProvider || 'None';
  const profileName = profiles.find((profile) => profile.id === currentProfile)?.name || currentProfile || 'Default';
  const taskModeName = taskModes.find((mode) => mode.id === currentTaskMode)?.name || currentTaskMode || 'None';

  const updateDraftSetting = (key: 'provider' | 'model' | 'systemPromptId' | 'taskPromptId', value: string) => {
    if (key === 'provider') {
      patchDraftSettings({ provider: value, model: '' });
      void wsClient.loadModels(value);
      return;
    }
    patchDraftSettings({ [key]: value } as Partial<DraftSettings>);
  };

  const openToTab = (tab: RightPanelTab) => {
    setRightPanelTab(tab);
    setRightPanelOpen(true);
  };

  const railBtn = (tab: RightPanelTab, Icon: typeof Activity, label: string) => {
    const active = rightPanelTab === tab;
    return (
      <button
        onClick={() => openToTab(tab)}
        className={`flex h-8 w-8 items-center justify-center rounded-xl transition-all duration-150 ${
          active
            ? 'bg-operator-accent/10 text-operator-accent'
            : 'bg-operator-panel text-operator-muted hover:text-operator-accent'
        }`}
        title={label}
      >
        <Icon className="w-3.5 h-3.5" />
      </button>
    );
  };

  const tabs: { id: RightPanelTab; label: string; icon: typeof Activity; badge?: number }[] = [
    { id: 'inbox', label: 'Inbox', icon: Inbox, badge: urgentCount || undefined },
    { id: 'runtime', label: 'Runtime', icon: Settings2 },
    { id: 'artifacts', label: 'Artifacts', icon: Package },
    { id: 'activity', label: 'Activity', icon: Layers },
    { id: 'approvals', label: 'Approvals', icon: ShieldAlert, badge: pendingCount || undefined },
  ];
  const activeTab = tabs.find((tab) => tab.id === rightPanelTab) || tabs[0];

  const tabLabels = useMemo(() => {
    if (panelWidth > 450) {
      return { inbox: 'Inbox', runtime: 'Runtime', artifacts: 'Artifacts', activity: 'Activity', approvals: 'Approvals' } as const;
    }
    if (panelWidth > 340) {
      return { inbox: 'Inbox', runtime: 'Runtime', artifacts: 'Files', activity: 'Runs', approvals: 'Queue' } as const;
    }
    return { inbox: 'Inbox', runtime: 'Run', artifacts: 'Files', activity: 'Runs', approvals: 'Queue' } as const;
  }, [panelWidth]);
  const compactTabs = !mobile && panelWidth > 0 && panelWidth < 340;
  if (!rightPanelOpen && !mobile) {
    return (
      <aside className="w-11 bg-operator-bg flex flex-col h-full items-center py-3 gap-3">
        <button
          onClick={() => setRightPanelOpen(true)}
          className="flex h-8 w-8 items-center justify-center rounded-xl text-operator-muted hover:text-operator-accent hover:bg-operator-panel transition-all duration-150"
          title="Expand inspector panel"
        >
          <ChevronLeft className="w-3.5 h-3.5" />
        </button>
        {railBtn('inbox', Inbox, 'Inbox')}
        {railBtn('runtime', Settings2, 'Runtime')}
        {railBtn('artifacts', Package, 'Artifacts')}
        {railBtn('activity', Layers, 'Activity')}
        {railBtn('approvals', ShieldAlert, 'Approvals')}
        <div className="mt-auto">
          <span className="relative flex h-2 w-2">
            {wsStatus === 'connected' && (
              <span className="pulse-live absolute inline-flex h-full w-full rounded-full bg-operator-success opacity-60" />
            )}
            <span className={`relative inline-flex h-2 w-2 rounded-full ${wsStatus === 'connected' ? 'bg-operator-success' : 'bg-operator-error'}`} />
          </span>
        </div>
      </aside>
    );
  }

  return (
    <>
    <aside
      ref={panelRef}
      className={`${mobile ? 'w-full min-w-0 border-l-0' : 'w-full min-w-0 border-l'} border-operator-border bg-operator-bg flex h-full flex-col overflow-hidden`}
    >
      {/* Header */}
      <div className="px-3 py-3 border-b border-operator-border flex items-center gap-2">
        {!mobile && (
          <button
            onClick={() => setRightPanelOpen(false)}
            className="p-1 text-operator-muted hover:text-operator-accent transition-colors duration-150 rounded-lg"
            title="Collapse panel"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        )}
        <Activity className="w-3.5 h-3.5 text-operator-accent" />
        <div>
          <h2 className="font-semibold text-[12px] uppercase tracking-wider text-operator-text">Inspector</h2>
          <div className="text-[10px] text-operator-muted">Runtime, artifacts, and run telemetry.</div>
        </div>
      </div>

      {/* Tab strip */}
      {compactTabs ? (
        <div className="flex items-center gap-2 border-b border-operator-border bg-operator-panel/20 px-2 py-2 shrink-0">
          <label htmlFor="inspector-tab-select" className="sr-only">
            Select inspector panel
          </label>
          <select
            id="inspector-tab-select"
            value={rightPanelTab}
            onChange={(event) => setRightPanelTab(event.target.value as RightPanelTab)}
            className="w-full rounded-xl border border-operator-border bg-operator-panel px-2.5 py-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-operator-text outline-none transition-colors duration-150 hover:border-operator-accent/30 focus:border-operator-accent/40"
            title="Select inspector panel"
          >
            {tabs.map((tab) => (
              <option key={tab.id} value={tab.id}>
                {tab.label}
              </option>
            ))}
          </select>
        </div>
      ) : (
        <div className="flex border-b border-operator-border bg-operator-panel/20 px-2 pt-1.5 shrink-0">
          {tabs.map((tab) => {
            const active = rightPanelTab === tab.id;
            const Icon = tab.icon;
            return (
              <button
                key={tab.id}
                onClick={() => setRightPanelTab(tab.id)}
                className={`relative min-w-0 flex-1 overflow-hidden flex items-center justify-center gap-1 rounded-t-xl px-1.5 py-2.5 text-[9px] font-semibold uppercase tracking-[0.08em] transition-all duration-150 border-b-2 sm:px-2 sm:text-[10px] sm:tracking-[0.12em] ${
                  active
                    ? 'text-operator-accent border-operator-accent bg-operator-accent/5'
                    : 'text-operator-muted border-transparent hover:text-operator-text hover:bg-operator-panel/40'
                }`}
                title={tab.label}
              >
                <Icon className="w-3 h-3 shrink-0" />
                <span className="min-w-0 truncate">{tabLabels[tab.id]}</span>
                {tab.badge && tab.badge > 0 && (
                  <span className="absolute top-1 right-1 h-3.5 w-3.5 flex items-center justify-center rounded-full bg-operator-accent text-[8px] font-bold text-white leading-none">
                    {tab.badge > 9 ? '9+' : tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {/* Body — scrollable per tab */}
      <div className="flex-1 overflow-y-auto">
        {rightPanelTab === 'inbox' && (
          <OperatorActionCenter sessionKey={activeSessionKey} />
        )}
        {rightPanelTab === 'artifacts' && (
          <ArtifactsPanel sessionKey={activeSessionKey} isDraft={isDraft} />
        )}
        {rightPanelTab === 'activity' && (
          <RunActivityPanel sessionKey={activeSessionKey} isDraft={isDraft} />
        )}
        {rightPanelTab === 'approvals' && (
          <ApprovalQueuePanel sessionKey={activeSessionKey} />
        )}
        {rightPanelTab === 'runtime' && (
      <div className="flex flex-col gap-4 text-[12px]">

        {/* 1. Pending approval — shown first; operator can't miss it */}
        {pendingApproval && (
          <section className="px-3 pt-3">
            <ApprovalRequestCard approval={pendingApproval} />
          </section>
        )}

        {/* 2. Live tool feed — only while a run is active */}
        {activeRunId && (
          <section className="bg-operator-panel/20 rounded-xl border border-operator-accent/15 mx-3 mt-3 overflow-hidden">
            <LiveToolFeed />
          </section>
        )}

        <div className="px-3 pb-3 flex flex-col gap-4">
          {/* 3. Session Info */}
          <section>
            <div className="flex items-center gap-1.5 mb-2 text-operator-muted">
              <Info className="w-3.5 h-3.5" />
              <h3 className="font-semibold text-[10px] uppercase tracking-wider">Session Info</h3>
            </div>
            <div className="space-y-1.5 bg-operator-panel/40 p-2.5 rounded-xl border border-operator-border">
              <div className="flex justify-between">
                <span className="text-operator-muted">Status:</span>
                <span className={`font-semibold ${isDraft ? 'text-operator-accent' : 'text-operator-success'}`}>
                  {isDraft ? 'DRAFT' : 'LOCKED'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-operator-muted">Session:</span>
                <span className="text-operator-text">
                  {activeSession?.archived ? 'Archived' : isDraft ? 'Pending Create' : 'Active'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-operator-muted">Created:</span>
                <span className="text-operator-text">{timeAgo(activeSession?.createdAt)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-operator-muted">Updated:</span>
                <span className="text-operator-text">{timeAgo(activeSession?.updatedAt)}</span>
              </div>
            </div>
          </section>

          {/* 4. Runtime Info (provider / model / profile / mode) */}
          <section>
            <div className="flex items-center gap-1.5 mb-2 text-operator-muted">
              <Settings2 className="w-3.5 h-3.5" />
              <h3 className="font-semibold text-[10px] uppercase tracking-wider">Runtime Info</h3>
            </div>
            <div className="space-y-2.5 bg-operator-panel/40 p-2.5 rounded-xl border border-operator-border">
              <div className="flex justify-between items-center">
                <span className="text-operator-muted">Connection:</span>
                <span className={`flex items-center gap-1.5 font-semibold ${wsStatus === 'connected' ? 'text-operator-success' : 'text-operator-error'}`}>
                  <span className="relative flex h-1.5 w-1.5">
                    {wsStatus === 'connected' && (
                      <span className="pulse-live absolute inline-flex h-full w-full rounded-full bg-operator-success opacity-60" />
                    )}
                    <span className={`relative inline-flex h-1.5 w-1.5 rounded-full ${wsStatus === 'connected' ? 'bg-operator-success' : 'bg-operator-error'}`} />
                  </span>
                  {wsStatus.toUpperCase()}
                </span>
              </div>

              {isDraft ? (
                <>
                  <div className="rounded-lg border border-operator-accent/15 bg-operator-accent/5 px-2.5 py-2 text-[11px] leading-relaxed text-operator-muted">
                    Draft settings are local until the first send. Your first message will create and lock the session.
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-operator-muted text-[10px] font-semibold uppercase tracking-wider">Provider</span>
                    <select
                      value={currentProvider || ''}
                      onChange={(e) => updateDraftSetting('provider', e.target.value)}
                      className={selectClass}
                    >
                      <option value="" disabled>Select Provider</option>
                      {providers.map((provider) => (
                        <option key={provider.id} value={provider.id}>{provider.displayName}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-operator-muted text-[10px] font-semibold uppercase tracking-wider">Model</span>
                    <select
                      value={currentModel || ''}
                      onChange={(e) => updateDraftSetting('model', e.target.value)}
                      className={selectClass}
                    >
                      <option value="" disabled>Select Model</option>
                      {availableModels.map((model) => (
                        <option key={model.id} value={model.id}>{model.displayName}</option>
                      ))}
                    </select>
                    {!currentProvider && (
                      <div className="text-[10px] text-operator-muted">Pick a provider to load chat models.</div>
                    )}
                    {currentProvider && !providerHasModels && (
                      <div className="text-[10px] text-operator-muted">Loading models for {providerName}…</div>
                    )}
                    {currentProvider && providerHasModels && availableModels.length === 0 && (
                      <div className="text-[10px] text-operator-error">
                        No chat models available for this provider.
                      </div>
                    )}
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-operator-muted text-[10px] font-semibold uppercase tracking-wider">Profile</span>
                    <select
                      value={currentProfile || ''}
                      onChange={(e) => updateDraftSetting('systemPromptId', e.target.value)}
                      className={selectClass}
                    >
                      {profiles.map((profile) => (
                        <option key={profile.id} value={profile.id}>{profile.name}</option>
                      ))}
                    </select>
                  </div>
                  <div className="flex flex-col gap-1">
                    <span className="text-operator-muted text-[10px] font-semibold uppercase tracking-wider">Mode</span>
                    <select
                      value={currentTaskMode || ''}
                      onChange={(e) => updateDraftSetting('taskPromptId', e.target.value)}
                      className={selectClass}
                    >
                      {taskModes.map((mode) => (
                        <option key={mode.id} value={mode.id}>{mode.name}</option>
                      ))}
                    </select>
                  </div>
                </>
              ) : (
                <div className="space-y-1.5 mt-1">
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <span className="text-operator-muted">Provider:</span>
                    <span className="min-w-0 flex-1 truncate text-right font-medium text-operator-text" title={providerName}>{providerName}</span>
                  </div>
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <span className="text-operator-muted">Model:</span>
                    <span className="min-w-0 flex-1 truncate text-right font-medium text-operator-text" title={activeSession.model || ''}>
                      {activeSession.model || 'None'}
                    </span>
                  </div>
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <span className="text-operator-muted">Profile:</span>
                    <span className="min-w-0 flex-1 truncate text-right font-medium text-operator-text" title={profileName}>{profileName}</span>
                  </div>
                  <div className="flex min-w-0 items-start justify-between gap-3">
                    <span className="text-operator-muted">Mode:</span>
                    <span className="min-w-0 flex-1 truncate text-right font-medium text-operator-text" title={taskModeName}>{taskModeName}</span>
                  </div>
                </div>
              )}
            </div>
          </section>

          {/* 5. Provider auth card — shown for openai-codex and any auth-requiring provider */}
          {(currentProvider === 'openai-codex' || (!isDraft && activeSession?.provider === 'openai-codex')) && (
            <section>
              <div className="flex items-center gap-1.5 mb-2 text-operator-muted">
                <ShieldAlert className="w-3.5 h-3.5" />
                <h3 className="font-semibold text-[10px] uppercase tracking-wider">Provider Auth</h3>
              </div>
              <ProviderAuthCard
                providerId="openai-codex"
                displayName="OpenAI Codex"
              />
            </section>
          )}

          {/* 6. Run Timeline — visible when a run is paused */}
          {pendingApproval && (
            <section>
              <div className="flex items-center gap-1.5 mb-2 text-operator-muted">
                <Activity className="w-3.5 h-3.5" />
                <h3 className="font-semibold text-[10px] uppercase tracking-wider">Run Timeline</h3>
              </div>
              <div className="bg-operator-panel/30 rounded-xl border border-operator-border overflow-hidden">
                <RunTimeline sessionKey={activeSessionKey} />
              </div>
            </section>
          )}

        </div>
      </div>
        )}
      </div>
    </aside>
    {/* Composer portal — always mounted, renders when composerOpen */}
    <SendMessageComposer />
    </>
  );
}
