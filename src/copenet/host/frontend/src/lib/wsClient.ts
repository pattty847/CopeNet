import { useAppStore } from '../store/useAppStore';
import {
  ChatEventPayload,
  EventFrame,
  IncomingFrame,
  Message,
  Model,
  Provider,
  PublicMessagePayload,
  ResponseFrame,
  Session,
  SessionExportPayload,
  SessionStateRecord,
  SessionRunRecord,
  ToolDescriptor,
  ToolExecution,
} from '../types/backend';

type PendingRequest = {
  resolve: (payload: Record<string, unknown>) => void;
  reject: (error: Error) => void;
};

const RECONNECT_DELAY_MS = 3000;
const DEFAULT_DEV_TOKEN = 'dev-token';
const PROVIDER_PRIORITY = ['lm-studio', 'ollama', 'codex-cli'];

function getWsUrl(): string {
  const envUrl = import.meta.env.VITE_COPNET_WS_URL?.trim();
  if (envUrl) return envUrl;
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

function getAuthToken(): string {
  const envToken = import.meta.env.VITE_COPNET_TOKEN?.trim() || '';
  const fromWindow = typeof window.COPNET_TOKEN === 'string' ? window.COPNET_TOKEN.trim() : '';
  const fromStorage = window.localStorage.getItem('copnet.token') || '';
  const fromMeta = document.querySelector('meta[name="copnet-token"]')?.getAttribute('content')?.trim() || '';
  return envToken || fromWindow || fromStorage || fromMeta || DEFAULT_DEV_TOKEN;
}

function pickPreferredProvider(providers: Provider[]): string {
  for (const id of PROVIDER_PRIORITY) {
    if (providers.some((provider) => provider.id === id && provider.available !== false)) return id;
  }
  return providers.find((provider) => provider.available !== false)?.id || providers[0]?.id || 'codex-cli';
}

function makeLocalId(prefix: string): string {
  return `${prefix}-${crypto.randomUUID()}`;
}

function normalizeToolExecution(raw: unknown): ToolExecution | null {
  if (!raw || typeof raw !== 'object') return null;
  const payload = raw as Record<string, unknown>;
  const toolId = String(payload.toolId || '').trim();
  if (!toolId) return null;
  return {
    toolId,
    ok: Boolean(payload.ok),
    summary: String(payload.summary || '').trim(),
    error: payload.error ? String(payload.error) : null,
  };
}

function normalizeSession(raw: unknown): Session {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    key: String(payload.key || ''),
    sessionId: String(payload.sessionId || ''),
    title: payload.title ? String(payload.title) : null,
    provider: String(payload.provider || ''),
    model: payload.model ? String(payload.model) : null,
    systemPromptId: payload.systemPromptId ? String(payload.systemPromptId) : null,
    taskPromptId: payload.taskPromptId ? String(payload.taskPromptId) : null,
    archived: Boolean(payload.archived),
    providerSessionId: payload.providerSessionId ? String(payload.providerSessionId) : null,
    createdAt: String(payload.createdAt || new Date().toISOString()),
    updatedAt: String(payload.updatedAt || new Date().toISOString()),
    lastRunId: payload.lastRunId ? String(payload.lastRunId) : null,
    inFlightRunId: payload.inFlightRunId ? String(payload.inFlightRunId) : null,
  };
}

function normalizeProvider(raw: unknown): Provider {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    displayName: String(payload.displayName || payload.id || ''),
    available: payload.available !== false,
    error: payload.error ? String(payload.error) : '',
    capabilities: (payload.capabilities as Record<string, boolean> | undefined) || {},
  };
}

function normalizeModel(raw: unknown): Model {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    displayName: String(payload.displayName || payload.id || ''),
    provider: String(payload.provider || ''),
    description: payload.description ? String(payload.description) : null,
    kind: String(payload.kind || 'chat'),
    capabilities: (payload.capabilities as Record<string, boolean> | undefined) || {},
    recommendedFor: Array.isArray(payload.recommendedFor) ? payload.recommendedFor.map(String) : [],
    metadata: (payload.metadata as Record<string, unknown> | undefined) || {},
  };
}

function normalizeTool(raw: unknown): ToolDescriptor {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    name: String(payload.name || payload.id || ''),
    description: String(payload.description || ''),
    category: String(payload.category || ''),
    inputSchema: (payload.inputSchema as Record<string, unknown> | undefined) || {},
    safetyLevel: String(payload.safetyLevel || ''),
    capabilities: Array.isArray(payload.capabilities) ? payload.capabilities.map(String) : [],
  };
}

function normalizePrompt(raw: unknown) {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    id: String(payload.id || ''),
    name: String(payload.name || payload.id || ''),
  };
}

function normalizeMessage(
  raw: PublicMessagePayload | null | undefined,
  sessionKey: string,
  localId: string,
  fallbackRole: Message['role'],
  fallbackState: Message['state'],
  optimistic = false,
): Message {
  return {
    localId,
    sessionKey,
    runId: raw?.runId ? String(raw.runId) : null,
    role: raw?.role === 'assistant' || raw?.role === 'system' ? raw.role : fallbackRole,
    content: typeof raw?.content === 'string' ? raw.content : '',
    timestamp: raw?.timestamp ? String(raw.timestamp) : new Date().toISOString(),
    provider: raw?.provider ? String(raw.provider) : null,
    model: raw?.model ? String(raw.model) : null,
    providerSessionId: raw?.providerSessionId ? String(raw.providerSessionId) : null,
    state: (raw?.state as Message['state']) || fallbackState,
    toolExecution: normalizeToolExecution(raw?.toolExecution),
    errorMessage: null,
    optimistic,
  };
}

class WsClient {
  private ws: WebSocket | null = null;
  private readonly url = getWsUrl();
  private reconnectTimer: number | null = null;
  private connectPromise: Promise<void> | null = null;
  private connectResolve: (() => void) | null = null;
  private connectReject: ((error: Error) => void) | null = null;
  private connectRequestId: string | null = null;
  private requestCounter = 0;
  private pendingRequests = new Map<string, PendingRequest>();
  private modelLoads = new Map<string, Promise<Model[]>>();

  async connect(): Promise<void> {
    if (this.ws && this.ws.readyState === WebSocket.OPEN && useAppStore.getState().wsStatus === 'connected') {
      return;
    }
    if (this.connectPromise) {
      return this.connectPromise;
    }

    const store = useAppStore.getState();
    store.setWsStatus('connecting');
    store.setAuthError(null);
    store.clearAppError();

    this.connectPromise = new Promise<void>((resolve, reject) => {
      this.connectResolve = resolve;
      this.connectReject = reject;
    });

    this.ws = new WebSocket(this.url);
    this.ws.onmessage = (event) => {
      void this.handleSocketMessage(String(event.data));
    };
    this.ws.onerror = () => {
      if (useAppStore.getState().wsStatus !== 'auth_failed') {
        useAppStore.getState().setAppError('WebSocket connection error.');
      }
    };
    this.ws.onclose = () => {
      const store = useAppStore.getState();
      if (store.wsStatus !== 'auth_failed') {
        store.setWsStatus('disconnected');
      }
      this.rejectAllPending(new Error('connection closed'));
      // Mark any in-flight assistant messages as aborted so the UI doesn't show a stuck spinner.
      const pending = store.pendingAssistants;
      for (const runId of Object.keys(pending)) {
        const target = pending[runId];
        store.updateMessage(target.sessionKey, target.localId, {
          state: 'aborted',
          errorMessage: 'Connection lost.',
          optimistic: false,
        });
        store.clearPendingAssistant(runId);
      }
      if (store.activeRunId) {
        store.setActiveRunId(null);
      }
      this.connectPromise = null;
      this.connectResolve = null;
      this.connectReject = null;
      this.connectRequestId = null;
      if (store.wsStatus !== 'auth_failed') {
        this.scheduleReconnect();
      }
    };

    return this.connectPromise;
  }

  private scheduleReconnect() {
    if (this.reconnectTimer !== null) {
      window.clearTimeout(this.reconnectTimer);
    }
    this.reconnectTimer = window.setTimeout(() => {
      void this.connect();
    }, RECONNECT_DELAY_MS);
  }

  private nextRequestId(method: string): string {
    this.requestCounter += 1;
    return `${method}-${this.requestCounter}`;
  }

  private sendFrame(frame: Record<string, unknown>) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      throw new Error('WebSocket is not connected');
    }
    this.ws.send(JSON.stringify(frame));
  }

  private async request<T extends Record<string, unknown>>(method: string, params: Record<string, unknown>): Promise<T> {
    await this.connect();
    const requestId = this.nextRequestId(method);
    return await new Promise<T>((resolve, reject) => {
      this.pendingRequests.set(requestId, {
        resolve: (payload) => resolve(payload as T),
        reject,
      });
      try {
        this.sendFrame({
          type: 'req',
          id: requestId,
          method,
          params,
        });
      } catch (error) {
        this.pendingRequests.delete(requestId);
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  private async handleSocketMessage(raw: string) {
    let frame: IncomingFrame;
    try {
      frame = JSON.parse(raw) as IncomingFrame;
    } catch (error) {
      console.error('Failed to parse WS message', error);
      return;
    }

    if (frame.type === 'event') {
      await this.handleEventFrame(frame);
      return;
    }
    this.handleResponseFrame(frame);
  }

  private async handleEventFrame(frame: EventFrame) {
    if (frame.event === 'connect.challenge') {
      const requestId = this.nextRequestId('connect');
      this.connectRequestId = requestId;
      this.sendFrame({
        type: 'req',
        id: requestId,
        method: 'connect',
        params: { auth: { token: getAuthToken() } },
      });
      return;
    }

    if (frame.event === 'chat') {
      this.handleChatEvent(frame.payload as unknown as ChatEventPayload);
    }
  }

  private handleResponseFrame(frame: ResponseFrame) {
    if (frame.id === this.connectRequestId) {
      if (frame.ok) {
        if (this.reconnectTimer !== null) {
          window.clearTimeout(this.reconnectTimer);
          this.reconnectTimer = null;
        }
        useAppStore.getState().setWsStatus('connected');
        this.connectResolve?.();
        this.connectPromise = null;
        this.connectResolve = null;
        this.connectReject = null;
        this.connectRequestId = null;
        void this.bootstrap();
      } else {
        const message = frame.error?.message || 'Authentication failed.';
        const store = useAppStore.getState();
        store.setWsStatus('auth_failed');
        store.setAuthError(message);
        this.connectReject?.(new Error(message));
        this.connectPromise = null;
        this.connectResolve = null;
        this.connectReject = null;
        this.connectRequestId = null;
        this.ws?.close();
      }
      return;
    }

    const pending = this.pendingRequests.get(frame.id);
    if (!pending) return;
    this.pendingRequests.delete(frame.id);
    if (!frame.ok) {
      pending.reject(new Error(frame.error?.message || 'Request failed'));
      return;
    }
    pending.resolve((frame.payload as Record<string, unknown> | undefined) || {});
  }

  private rejectAllPending(error: Error) {
    for (const [, pending] of this.pendingRequests) {
      pending.reject(error);
    }
    this.pendingRequests.clear();
  }

  private ensureDraftDefaults() {
    const store = useAppStore.getState();
    const preferredProvider = pickPreferredProvider(store.providers);
    const defaultProfile = store.profiles.find((item) => item.id === 'default')?.id || store.profiles[0]?.id || '';
    const defaultTaskMode = store.taskModes.find((item) => item.id === 'none')?.id || store.taskModes[0]?.id || '';
    const current = store.draftSettings;
    const nextProvider = store.providers.some((provider) => provider.id === current.provider && provider.available !== false)
      ? current.provider
      : preferredProvider;
    store.replaceDraftSettings({
      provider: nextProvider,
      model: nextProvider === current.provider ? current.model : '',
      systemPromptId: store.profiles.some((item) => item.id === current.systemPromptId) ? current.systemPromptId : defaultProfile,
      taskPromptId: store.taskModes.some((item) => item.id === current.taskPromptId) ? current.taskPromptId : defaultTaskMode,
    });
  }

  private async bootstrap() {
    try {
      const [providersPayload, toolsPayload, promptsPayload, sessionsPayload] = await Promise.all([
        this.request<{ providers: unknown[] }>('providers.list', {}),
        this.request<{ tools: unknown[] }>('tools.list', {}),
        this.request<{ profiles?: unknown[]; taskModes?: unknown[] }>('prompts.list', {}),
        this.request<{ sessions: unknown[] }>('sessions.list', { includeArchived: useAppStore.getState().showArchived }),
      ]);

      const store = useAppStore.getState();
      const providers = (providersPayload.providers || []).map(normalizeProvider);
      const sessions = (sessionsPayload.sessions || []).map(normalizeSession);
      store.setProviders(providers);
      store.setTools((toolsPayload.tools || []).map(normalizeTool));
      store.setPromptCatalog(
        (promptsPayload.profiles || []).map(normalizePrompt),
        (promptsPayload.taskModes || []).map(normalizePrompt),
      );
      store.setSessions(sessions);
      this.ensureDraftDefaults();

      const currentKey = store.activeSessionKey;
      const hasCurrent = currentKey && sessions.some((session) => session.key === currentKey);
      const nextKey = hasCurrent ? currentKey : store.draftOpen ? null : sessions[0]?.key || null;
      store.setActiveSessionKey(nextKey);
      if (nextKey) {
        store.setDraftOpen(false);
        await this.loadHistory(nextKey);
      }
    } catch (error) {
      useAppStore.getState().setAppError(error instanceof Error ? error.message : 'Bootstrap failed.');
    }
  }

  async refreshSessions() {
    const payload = await this.request<{ sessions: unknown[] }>('sessions.list', {
      includeArchived: useAppStore.getState().showArchived,
    });
    useAppStore.getState().setSessions((payload.sessions || []).map(normalizeSession));
  }

  async loadModels(providerId: string): Promise<Model[]> {
    const store = useAppStore.getState();
    if (store.loadedModelProviders[providerId]) {
      return store.modelsByProvider[providerId] || [];
    }

    const inFlight = this.modelLoads.get(providerId);
    if (inFlight) return inFlight;

    const promise = this.request<{ models: unknown[] }>('models.list', { provider: providerId, kind: 'chat' })
      .then((payload) => {
        const models = (payload.models || []).map(normalizeModel);
        useAppStore.getState().setModelsForProvider(providerId, models);
        this.modelLoads.delete(providerId);
        return models;
      })
      .catch((error) => {
        useAppStore.getState().setModelsForProvider(providerId, []);
        this.modelLoads.delete(providerId);
        throw error;
      });

    this.modelLoads.set(providerId, promise);
    return promise;
  }

  async loadHistory(sessionKey: string) {
    const payload = await this.request<{ sessionKey: string; messages: PublicMessagePayload[] }>('chat.history', {
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

  beginDraft() {
    const store = useAppStore.getState();
    store.setActiveSessionKey(null);
    store.setDraftOpen(true);
    store.clearAppError();
    this.ensureDraftDefaults();
  }

  async renameSession(key: string, title: string) {
    const payload = await this.request<{ session: unknown }>('sessions.rename', { key, title: title || undefined });
    if (payload.session) {
      useAppStore.getState().upsertSession(normalizeSession(payload.session));
    }
  }

  async archiveSession(key: string, archived: boolean) {
    const payload = await this.request<{ session: unknown }>('sessions.archive', { key, archived });
    if (payload.session) {
      useAppStore.getState().upsertSession(normalizeSession(payload.session));
    }
    const store = useAppStore.getState();
    if (!archived) {
      // Restoring: switch to active view and re-select the session so it's immediately visible.
      store.setShowArchived(false);
      store.setActiveSessionKey(key);
      store.setDraftOpen(false);
    } else if (store.activeSessionKey === key) {
      // Archiving the currently active session — deselect it.
      store.setActiveSessionKey(null);
    }
    await this.refreshSessions();
  }

  async debugCopySession(key: string): Promise<Session> {
    const payload = await this.request<{ session: unknown }>('sessions.debugCopy', { key });
    const session = normalizeSession(payload.session);
    const store = useAppStore.getState();
    store.upsertSession(session);
    store.setShowArchived(false);
    store.setActiveSessionKey(session.key);
    store.setDraftOpen(false);
    await this.refreshSessions();
    await this.loadHistory(session.key);
    return session;
  }

  async exportSession(key: string): Promise<SessionExportPayload> {
    const payload = await this.request<{
      session: unknown;
      messages: PublicMessagePayload[];
      markdown: string;
    }>('sessions.export', { key });
    return {
      session: normalizeSession(payload.session),
      messages: (payload.messages || []).map((message) => message),
      markdown: String(payload.markdown || ''),
    };
  }

  async listSessionRuns(key: string, limit = 20): Promise<SessionRunRecord[]> {
    const payload = await this.request<{ runs?: SessionRunRecord[] }>('sessions.runs', { key, limit });
    return Array.isArray(payload.runs) ? payload.runs : [];
  }

  async resolveSessionRun(key: string, runId: string): Promise<SessionRunRecord | null> {
    const payload = await this.request<{ run?: SessionRunRecord | null }>('sessions.run', { key, runId });
    return payload.run ?? null;
  }

  async resolveSessionState(key: string): Promise<SessionStateRecord | null> {
    const payload = await this.request<{ state?: SessionStateRecord | null }>('sessions.state', { key });
    return payload.state ?? null;
  }

  async sendMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed) return;

    const store = useAppStore.getState();
    store.clearAppError();

    let session = store.sessions.find((item) => item.key === store.activeSessionKey) || null;
    if (!session) {
      const draft = store.draftSettings;
      const createPayload = await this.request<{ session: unknown }>('sessions.create', {
        provider: draft.provider,
        model: draft.model || undefined,
        systemPromptId: draft.systemPromptId || undefined,
        taskPromptId: draft.taskPromptId || undefined,
      });
      session = normalizeSession(createPayload.session);
      store.upsertSession(session);
      store.setActiveSessionKey(session.key);
      store.setDraftOpen(false);
    }

    const userMessage: Message = {
      localId: makeLocalId('user'),
      sessionKey: session.key,
      runId: null,
      role: 'user',
      content: trimmed,
      timestamp: new Date().toISOString(),
      provider: session.provider,
      model: session.model,
      providerSessionId: session.providerSessionId,
      state: 'final',
      toolExecution: null,
      errorMessage: null,
      optimistic: true,
    };
    store.addMessage(session.key, userMessage);

    try {
      const payload = await this.request<{ runId?: string; status?: string }>('chat.send', {
        sessionKey: session.key,
        message: trimmed,
        provider: session.provider,
        model: session.model || undefined,
        systemPromptId: session.systemPromptId || undefined,
        taskPromptId: session.taskPromptId || undefined,
      });
      const runId = payload.runId ? String(payload.runId) : null;
      const status = payload.status ? String(payload.status) : '';

      if (status === 'in_flight') {
        throw new Error('This session already has a reply in progress.');
      }

      if (runId) {
        const assistantMessage: Message = {
          localId: makeLocalId('assistant'),
          sessionKey: session.key,
          runId,
          role: 'assistant',
          content: '',
          timestamp: new Date().toISOString(),
          provider: session.provider,
          model: session.model,
          providerSessionId: session.providerSessionId,
          state: 'delta',
          toolExecution: null,
          errorMessage: null,
          optimistic: true,
        };
        store.addMessage(session.key, assistantMessage);
        store.registerPendingAssistant(runId, session.key, assistantMessage.localId);
        store.setActiveRunId(runId);
      }
    } catch (error) {
      store.setAppError(error instanceof Error ? error.message : 'Unable to send message.');
      store.addMessage(session.key, {
        localId: makeLocalId('system'),
        sessionKey: session.key,
        runId: null,
        role: 'system',
        content: error instanceof Error ? error.message : 'Unable to send message.',
        timestamp: new Date().toISOString(),
        provider: null,
        model: null,
        providerSessionId: null,
        state: 'error',
        toolExecution: null,
        errorMessage: error instanceof Error ? error.message : 'Unable to send message.',
        optimistic: false,
      });
      throw error;
    }
  }

  async abortActiveRun() {
    const store = useAppStore.getState();
    if (!store.activeRunId && !store.activeSessionKey) return;
    await this.request('chat.abort', {
      sessionKey: store.activeSessionKey || undefined,
      runId: store.activeRunId || undefined,
    });
  }

  private handleChatEvent(payload: ChatEventPayload) {
    const store = useAppStore.getState();
    const runId = payload.runId ? String(payload.runId) : null;
    const sessionKey = payload.sessionKey;
    const toolExecution = normalizeToolExecution(payload.toolExecution);

    if (payload.state === 'delta') {
      let target = runId ? useAppStore.getState().pendingAssistants[runId] : undefined;
      if (runId && !target) {
        const localId = makeLocalId('assistant');
        store.addMessage(sessionKey, {
          localId,
          sessionKey,
          runId,
          role: 'assistant',
          content: '',
          timestamp: new Date().toISOString(),
          provider: payload.provider ? String(payload.provider) : null,
          model: payload.model ? String(payload.model) : null,
          providerSessionId: payload.message?.providerSessionId ? String(payload.message.providerSessionId) : null,
          state: 'delta',
          toolExecution,
          errorMessage: null,
          optimistic: true,
        });
        store.registerPendingAssistant(runId, sessionKey, localId);
        target = { sessionKey, localId };
      }

      if (target) {
        const existing = useAppStore.getState().messages[target.sessionKey]?.find((message) => message.localId === target.localId);
        const chunk = payload.message?.content ? String(payload.message.content) : '';
        store.updateMessage(target.sessionKey, target.localId, {
          content: `${existing?.content || ''}${chunk}`,
          provider: payload.provider ? String(payload.provider) : existing?.provider || null,
          model: payload.model ? String(payload.model) : existing?.model || null,
          state: 'delta',
          toolExecution: toolExecution || existing?.toolExecution || null,
          optimistic: true,
        });
      }
      return;
    }

    if (payload.state === 'final' || payload.state === 'error' || payload.state === 'aborted') {
      const target = runId ? useAppStore.getState().pendingAssistants[runId] : undefined;
      if (target) {
        const existing = useAppStore.getState().messages[target.sessionKey]?.find((message) => message.localId === target.localId);
        store.updateMessage(target.sessionKey, target.localId, {
          content:
            typeof payload.message?.content === 'string' && payload.message.content.length > 0
              ? payload.message.content
              : existing?.content || '',
          provider: payload.provider ? String(payload.provider) : existing?.provider || null,
          model: payload.model ? String(payload.model) : existing?.model || null,
          state: payload.state,
          toolExecution: toolExecution || existing?.toolExecution || null,
          errorMessage: payload.errorMessage ? String(payload.errorMessage) : null,
          optimistic: false,
        });
        if (runId) {
          store.clearPendingAssistant(runId);
        }
      } else if (payload.state === 'error') {
        store.addMessage(sessionKey, {
          localId: makeLocalId('system'),
          sessionKey,
          runId,
          role: 'system',
          content: payload.errorMessage ? String(payload.errorMessage) : 'Run failed.',
          timestamp: new Date().toISOString(),
          provider: payload.provider ? String(payload.provider) : null,
          model: payload.model ? String(payload.model) : null,
          providerSessionId: null,
          state: 'error',
          toolExecution,
          errorMessage: payload.errorMessage ? String(payload.errorMessage) : 'Run failed.',
          optimistic: false,
        });
      }

      if (runId && store.activeRunId === runId) {
        store.setActiveRunId(null);
      }
      // Only close the draft if the completed run belongs to the currently active session.
      // Closing unconditionally would destroy a new draft the user opened while a prior run finished.
      if (sessionKey && store.activeSessionKey === sessionKey) {
        store.setDraftOpen(false);
      }
      void this.refreshSessions();
    }
  }
}

export const wsClient = new WsClient();
