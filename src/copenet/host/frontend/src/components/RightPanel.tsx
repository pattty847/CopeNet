import React from 'react';
import { useAppStore } from '../store/useAppStore';
import { wsClient } from '../lib/wsClient';
import { Activity, Info, Settings2, TerminalSquare } from 'lucide-react';

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

export function RightPanel() {
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

  const activeSession = sessions.find((session) => session.key === activeSessionKey) || null;
  const messages = activeSessionKey ? messagesMap[activeSessionKey] || [] : [];
  const isDraft = !activeSession;

  const currentProvider = isDraft ? draftSettings.provider : activeSession.provider;
  const currentModel = isDraft ? draftSettings.model : activeSession.model || '';
  const currentProfile = isDraft ? draftSettings.systemPromptId : activeSession.systemPromptId || '';
  const currentTaskMode = isDraft ? draftSettings.taskPromptId : activeSession.taskPromptId || '';
  const availableModels = currentProvider ? modelsByProvider[currentProvider] || [] : [];

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

  const providerName = providers.find((provider) => provider.id === currentProvider)?.displayName || currentProvider || 'None';

  const updateDraftSetting = (key: 'provider' | 'model' | 'systemPromptId' | 'taskPromptId', value: string) => {
    if (key === 'provider') {
      patchDraftSettings({ provider: value, model: '' });
      void wsClient.loadModels(value);
      return;
    }
    patchDraftSettings({ [key]: value } as never);
  };

  return (
    <aside className="w-80 border-l border-operator-border bg-operator-bg flex flex-col h-full overflow-y-auto">
      <div className="p-4 border-b border-operator-border flex items-center gap-2">
        <Activity className="w-4 h-4 text-operator-accent" />
        <h2 className="font-bold font-mono text-sm text-operator-text">TELEMETRY</h2>
      </div>

      <div className="p-4 flex flex-col gap-6 font-mono text-sm">
        <section>
          <div className="flex items-center gap-2 mb-3 text-operator-muted">
            <Info className="w-4 h-4" />
            <h3 className="font-bold text-xs uppercase tracking-wider">Session Info</h3>
          </div>
          <div className="space-y-2 bg-operator-panel/50 p-3 rounded border border-operator-border">
            <div className="flex justify-between">
              <span className="text-operator-muted">Status:</span>
              <span className={isDraft ? 'text-operator-accent' : 'text-operator-success'}>
                {isDraft ? 'DRAFT' : 'LOCKED'}
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

        <section>
          <div className="flex items-center gap-2 mb-3 text-operator-muted">
            <Settings2 className="w-4 h-4" />
            <h3 className="font-bold text-xs uppercase tracking-wider">Runtime Info</h3>
          </div>
          <div className="space-y-3 bg-operator-panel/50 p-3 rounded border border-operator-border">
            <div className="flex justify-between items-center">
              <span className="text-operator-muted">Connection:</span>
              <span className={`flex items-center gap-1 ${wsStatus === 'connected' ? 'text-operator-success' : 'text-operator-error'}`}>
                <div className={`w-2 h-2 rounded-full ${wsStatus === 'connected' ? 'bg-operator-success' : 'bg-operator-error'}`} />
                {wsStatus.toUpperCase()}
              </span>
            </div>

            {isDraft ? (
              <>
                <div className="flex flex-col gap-1.5 mt-2">
                  <span className="text-operator-muted text-[10px] uppercase tracking-wider">Provider</span>
                  <select
                    value={currentProvider || ''}
                    onChange={(e) => updateDraftSetting('provider', e.target.value)}
                    className="bg-operator-bg border border-operator-border text-operator-text text-xs font-mono px-2 py-1.5 rounded-sm focus:outline-none focus:border-operator-accent w-full"
                  >
                    <option value="" disabled>Select Provider</option>
                    {providers.map((provider) => (
                      <option key={provider.id} value={provider.id}>{provider.displayName}</option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <span className="text-operator-muted text-[10px] uppercase tracking-wider">Model</span>
                  <select
                    value={currentModel || ''}
                    onChange={(e) => updateDraftSetting('model', e.target.value)}
                    className="bg-operator-bg border border-operator-border text-operator-text text-xs font-mono px-2 py-1.5 rounded-sm focus:outline-none focus:border-operator-accent w-full"
                  >
                    <option value="" disabled>Select Model</option>
                    {availableModels.map((model) => (
                      <option key={model.id} value={model.id}>{model.displayName}</option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <span className="text-operator-muted text-[10px] uppercase tracking-wider">Profile</span>
                  <select
                    value={currentProfile || ''}
                    onChange={(e) => updateDraftSetting('systemPromptId', e.target.value)}
                    className="bg-operator-bg border border-operator-border text-operator-text text-xs font-mono px-2 py-1.5 rounded-sm focus:outline-none focus:border-operator-accent w-full"
                  >
                    {profiles.map((profile) => (
                      <option key={profile.id} value={profile.id}>{profile.name}</option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <span className="text-operator-muted text-[10px] uppercase tracking-wider">Mode</span>
                  <select
                    value={currentTaskMode || ''}
                    onChange={(e) => updateDraftSetting('taskPromptId', e.target.value)}
                    className="bg-operator-bg border border-operator-border text-operator-text text-xs font-mono px-2 py-1.5 rounded-sm focus:outline-none focus:border-operator-accent w-full"
                  >
                    {taskModes.map((mode) => (
                      <option key={mode.id} value={mode.id}>{mode.name}</option>
                    ))}
                  </select>
                </div>
              </>
            ) : (
              <div className="space-y-2 mt-2">
                <div className="flex justify-between">
                  <span className="text-operator-muted">Provider:</span>
                  <span className="text-operator-text truncate max-w-[120px] text-right" title={providerName}>{providerName}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-operator-muted">Model:</span>
                  <span className="text-operator-text truncate max-w-[120px] text-right" title={activeSession.model || ''}>
                    {activeSession.model || 'None'}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-operator-muted">Profile:</span>
                  <span className="text-operator-text">{activeSession.systemPromptId || 'default'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-operator-muted">Mode:</span>
                  <span className="text-operator-text">{activeSession.taskPromptId || 'none'}</span>
                </div>
              </div>
            )}
          </div>
        </section>

        <section>
          <div className="flex items-center gap-2 mb-3 text-operator-muted">
            <TerminalSquare className="w-4 h-4" />
            <h3 className="font-bold text-xs uppercase tracking-wider">Latest Tool Activity</h3>
          </div>
          <div className="bg-operator-panel/50 p-3 rounded border border-operator-border">
            {latestTool ? (
              <div className="space-y-2">
                <div className="flex justify-between items-center">
                  <span className="text-operator-text font-bold truncate">{latestTool.toolId}</span>
                  <span className={`text-xs ${latestTool.ok ? 'text-operator-success' : 'text-operator-error'}`}>
                    {latestTool.ok ? 'SUCCESS' : 'ERROR'}
                  </span>
                </div>
                <div className="text-xs text-operator-muted truncate">{latestTool.summary}</div>
              </div>
            ) : (
              <div className="text-operator-muted text-xs text-center py-2">
                No tools executed yet.
              </div>
            )}
          </div>
        </section>
      </div>
    </aside>
  );
}
