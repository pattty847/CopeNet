import { useAppStore } from '../store/useAppStore';
import type { Message, Provider, PublicMessagePayload, Session } from '../types/backend';
import { DRAFT_TRANSCRIPT_SESSION_KEY } from './personaCommands';
import { normalizeMessage, normalizeSession } from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

const PROVIDER_PRIORITY = ['lm-studio', 'ollama', 'openai-codex'];

function pickPreferredProvider(providers: Provider[]): string {
  for (const id of PROVIDER_PRIORITY) {
    if (providers.some((provider) => provider.id === id && provider.available !== false)) return id;
  }
  return providers.find((provider) => provider.available !== false)?.id || providers[0]?.id || 'openai-codex';
}

export function ensureDraftDefaultsAction(): void {
  const store = useAppStore.getState();
  const preferredProvider = pickPreferredProvider(store.providers);
  const defaultProfile = store.profiles.find((item) => item.id === 'default')?.id || store.profiles[0]?.id || '';
  const defaultTaskMode = store.taskModes.find((item) => item.id === 'none')?.id || store.taskModes[0]?.id || '';
  const current = store.draftSettings;
  const nextProvider = store.providers.some((provider) => provider.id === current.provider && provider.available !== false)
    ? current.provider
    : preferredProvider;
  const knownModels = store.loadedModelProviders[nextProvider] ? store.modelsByProvider[nextProvider] || [] : [];
  const nextModel = nextProvider === current.provider
    ? (!knownModels.length || knownModels.some((item) => item.id === current.model) ? current.model : '')
    : '';
  const personaSettings = store.personaSettings;
  store.replaceDraftSettings({
    provider: nextProvider,
    model: nextModel,
    systemPromptId: store.profiles.some((item) => item.id === current.systemPromptId) ? current.systemPromptId : defaultProfile,
    taskPromptId: store.taskModes.some((item) => item.id === current.taskPromptId) ? current.taskPromptId : defaultTaskMode,
    personaId: current.personaId || personaSettings?.defaultPersonaId || 'default',
    personaFlavorId: current.personaFlavorId || '',
    personaPrivacyTier: current.personaPrivacyTier || personaSettings?.defaultPrivacyTier || 'private',
    workspaceRoot: current.workspaceRoot || store.runtimeContext?.workspaceRoot || '',
  });
}

export async function refreshSessionsAction(request: WsRpcRequest): Promise<void> {
  const payload = await request<{ sessions: unknown[] }>('sessions.list', {
    includeArchived: useAppStore.getState().showArchived,
  });
  useAppStore.getState().setSessions((payload.sessions || []).map(normalizeSession));
}

export async function loadHistoryAction(request: WsRpcRequest, sessionKey: string): Promise<void> {
  const payload = await request<{ sessionKey: string; messages: PublicMessagePayload[] }>('chat.history', {
    sessionKey,
    limit: 200,
  });
  const normalized = (payload.messages || []).map((message, index) =>
    normalizeMessage(
      message,
      sessionKey,
      `history-${sessionKey}-${index}-${message.timestamp || index}`,
      (message.role as Message['role']) || 'assistant',
      (message.state as Message['state']) || 'final',
    ),
  );
  useAppStore.getState().setMessages(sessionKey, normalized);
}

export function beginDraftAction(): void {
  const store = useAppStore.getState();
  store.setActiveSessionKey(null);
  store.setDraftOpen(true);
  store.setDraftStarterIntent(null);
  store.setMessages(DRAFT_TRANSCRIPT_SESSION_KEY, []);
  store.setSessionDrawerOpen(false);
  store.setInspectorTarget(null);
  store.clearAppError();
  ensureDraftDefaultsAction();
}

export async function renameSessionAction(request: WsRpcRequest, key: string, title: string): Promise<void> {
  const payload = await request<{ session: unknown }>('sessions.rename', { key, title: title || undefined });
  if (payload.session) {
    useAppStore.getState().upsertSession(normalizeSession(payload.session));
  }
}

export async function archiveSessionAction(
  request: WsRpcRequest,
  refreshSessions: () => Promise<void>,
  key: string,
  archived: boolean,
): Promise<void> {
  const payload = await request<{ session: unknown }>('sessions.archive', { key, archived });
  if (payload.session) {
    useAppStore.getState().upsertSession(normalizeSession(payload.session));
  }
  const store = useAppStore.getState();
  if (!archived) {
    store.setShowArchived(false);
    store.setActiveSessionKey(key);
    store.setDraftOpen(false);
  } else if (store.activeSessionKey === key) {
    store.setActiveSessionKey(null);
  }
  await refreshSessions();
}

export async function debugCopySessionAction(
  request: WsRpcRequest,
  refreshSessions: () => Promise<void>,
  loadHistory: (sessionKey: string) => Promise<void>,
  key: string,
): Promise<Session> {
  const payload = await request<{ session: unknown }>('sessions.debugCopy', { key });
  const session = normalizeSession(payload.session);
  const store = useAppStore.getState();
  store.upsertSession(session);
  store.setShowArchived(false);
  store.setActiveSessionKey(session.key);
  store.setDraftOpen(false);
  await refreshSessions();
  await loadHistory(session.key);
  return session;
}
