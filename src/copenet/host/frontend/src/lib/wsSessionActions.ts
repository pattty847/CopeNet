import { useAppStore } from '../store/useAppStore';
import type { Message, PublicMessagePayload, Session } from '../types/backend';
import { DRAFT_TRANSCRIPT_SESSION_KEY } from './personaCommands';
import { normalizeMessage, normalizeSession } from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

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

export function beginDraftAction(ensureDraftDefaults: () => void): void {
  const store = useAppStore.getState();
  store.setActiveSessionKey(null);
  store.setDraftOpen(true);
  store.setDraftStarterIntent(null);
  store.setMessages(DRAFT_TRANSCRIPT_SESSION_KEY, []);
  store.setSessionDrawerOpen(false);
  store.setInspectorTarget(null);
  store.clearAppError();
  ensureDraftDefaults();
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
