import { useAppStore } from '../store/useAppStore';
import {
  ApprovalRequest,
  ChatEventPayload,
  EventFrame,
  IncomingFrame,
  IdentityContextPayload,
  IdentityContextRuntime,
  LiveToolCall,
  MemoryItem,
  MessageDestination,
  Message,
  MessagePart,
  MessagingConfig,
  Model,
  PatProfile,
  PersonaContextPayload,
  ApodResult,
  PersonaFlavorDraft,
  PersonaHomeSummary,
  PersonaListItem,
  PersonaSettings,
  PromptOptimizationResult,
  PulseRecord,
  ProfileChangelogItem,
  ProviderAuthStatus,
  PublicMessagePayload,
  RuntimeContext,
  WorkspaceIntelSummary,
  ReturnBriefingPayload,
  ResponseFrame,
  Session,
  SessionMergeState,
  SessionExportPayload,
  SessionArtifactRecord,
  SessionStateRecord,
  SessionRunRecord,
  TextPart,
  TelegramSessionRoute,
  ToolDescriptor,
  ToolEffect,
  ToolExecution,
  ToolResultPreview,
  TurnStateSnapshot,
  WorkspaceFile,
  WorkspaceFileContent,
  ShellAllowlistEntry,
} from '../types/backend';
import { DRAFT_TRANSCRIPT_SESSION_KEY } from './personaCommands';
import {
  buildBatchLabel,
  makeLocalId,
  normalizeApprovalRequest,
  normalizeAssistantDisplayText,
  normalizeDestination,
  normalizeIdentityContext,
  normalizeIdentityContextRuntime,
  normalizeMemoryItem,
  normalizeMergeState,
  normalizeMessage,
  normalizeMessageParts,
  normalizeMessagingConfig,
  normalizePatProfile,
  normalizePersonaContext,
  normalizePersonaFlavorDraft,
  normalizePersonaHome,
  normalizePersonaSettings,
  normalizeProfileChangelogItem,
  normalizePrompt,
  normalizeProvider,
  normalizePulse,
  normalizeReturnBriefing,
  normalizeRuntimeContext,
  normalizeSession,
  normalizeTelegramRoute,
  normalizeTool,
  normalizeToolEffect,
  normalizeToolExecution,
  normalizeToolResultPreview,
  normalizeWorkspaceIntelSummary,
} from './wsNormalizers';
import {
  deleteMessagingDestinationRpc,
  deleteMessagingRouteRpc,
  getMessagingConfigRpc,
  listMessagingDestinationsRpc,
  listMessagingRoutesRpc,
  testMessagingPlatformRpc,
  updateMessagingApprovalPolicyRpc,
  updateTelegramRuntimeDefaultsRpc,
  upsertMessagingDestinationRpc,
  upsertMessagingRouteRpc,
} from './wsMessagingRpc';
import {
  approveMemoryRpc,
  archiveMemoryRpc,
  createPersonaRpc,
  discardMemoryRpc,
  draftPersonaFlavorRpc,
  getPersonaContextRpc,
  getPersonaSummaryRpc,
  listPersonasRpc,
  refreshMemoryDraftsRpc,
  savePersonaFlavorRpc,
  selectPersonaRpc,
  updatePersonaSettingsRpc,
  upsertMemoryRpc,
} from './wsIdentityRpc';
import {
  addShellAllowlistRpc,
  createPulseFromSessionRpc,
  dismissPulseRpc,
  fetchApodRpc,
  listPulsesRpc,
  listShellAllowlistRpc,
  listWorkspaceFilesRpc,
  optimizePromptRpc,
  providerAuthBeginLoginRpc,
  providerAuthLogoutRpc,
  providerAuthStatusRpc,
  readPersonaFileRpc,
  readWorkspaceFileRpc,
  removeShellAllowlistRpc,
  savePulsesRpc,
  writePersonaFileRpc,
  writeWorkspaceFileRpc,
} from './wsSupportRpc';
import {
  createMergedSessionRpc,
  exportSessionRpc,
  listSessionArtifactsRpc,
  listSessionRunsRpc,
  resolveMergeStateRpc,
  resolveSessionRunRpc,
  resolveSessionStateRpc,
  revertEditRpc,
} from './wsSessionRpc';
import { browseWorkspaceRootRpc, setWorkspaceRootRpc } from './wsRuntimeRpc';
import { loadModelsAction } from './wsCatalogActions';
import { abortActiveRunAction, decideApprovalAction } from './wsChatActions';
import {
  archiveSessionAction,
  beginDraftAction,
  debugCopySessionAction,
  ensureDraftDefaultsAction,
  loadHistoryAction,
  refreshSessionsAction,
  renameSessionAction,
} from './wsSessionActions';
export { normalizeAssistantDisplayText } from './wsNormalizers';

type PendingRequest = {
  resolve: (payload: Record<string, unknown>) => void;
  reject: (error: Error) => void;
};

const RECONNECT_DELAY_MS = 3000;
const CONNECT_TIMEOUT_MS = 10000;
const REQUEST_TIMEOUT_MS = 15000;
const DEFAULT_DEV_TOKEN = 'dev-token';

function getEnvString(name: 'VITE_COPNET_WS_URL' | 'VITE_COPNET_TOKEN'): string {
  const meta = typeof import.meta !== 'undefined' ? (import.meta as ImportMeta & { env?: Record<string, unknown> }) : undefined;
  const value = meta?.env?.[name];
  return typeof value === 'string' ? value.trim() : '';
}

function getWsUrl(): string {
  const envUrl = getEnvString('VITE_COPNET_WS_URL');
  if (envUrl) return envUrl;
  if (typeof window === 'undefined') return 'ws://127.0.0.1:17123/ws';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

function getAuthToken(): string {
  const envToken = getEnvString('VITE_COPNET_TOKEN');
  const fromWindow = typeof window !== 'undefined' && typeof window.COPNET_TOKEN === 'string' ? window.COPNET_TOKEN.trim() : '';
  const fromStorage = typeof window !== 'undefined' ? window.localStorage.getItem('copnet.token') || '' : '';
  const fromMeta = typeof document !== 'undefined' ? document.querySelector('meta[name="copnet-token"]')?.getAttribute('content')?.trim() || '' : '';
  return envToken || fromWindow || fromStorage || fromMeta || DEFAULT_DEV_TOKEN;
}

class WsClient {
  private ws: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private connectPromise: Promise<void> | null = null;
  private connectResolve: (() => void) | null = null;
  private connectReject: ((error: Error) => void) | null = null;
  private connectRequestId: string | null = null;
  private connectTimeoutTimer: number | null = null;
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
    this.connectTimeoutTimer = window.setTimeout(() => {
      const error = new Error(`WebSocket connect timed out after ${CONNECT_TIMEOUT_MS / 1000}s.`);
      this.connectReject?.(error);
      store.setWsStatus('disconnected');
      store.setAppError(error.message);
      this.connectPromise = null;
      this.connectResolve = null;
      this.connectReject = null;
      this.connectRequestId = null;
      this.connectTimeoutTimer = null;
      this.ws?.close();
    }, CONNECT_TIMEOUT_MS);

    this.ws = new WebSocket(getWsUrl());
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
      // Phase 4.6: the backend keeps in-flight runs alive across a socket drop,
      // so do NOT false-abort pending assistants here. Mark them "reconnecting"
      // and KEEP them tracked + keep activeRunId, so bootstrap() can reattach /
      // reconcile against the persisted run on reconnect. A run is only marked
      // aborted when the backend confirms it (chat.aborted) or its final record.
      const pending = store.pendingAssistants;
      for (const runId of Object.keys(pending)) {
        const target = pending[runId];
        store.updateMessage(target.sessionKey, target.localId, {
          reconnecting: true,
          errorMessage: null,
        });
      }
      this.connectPromise = null;
      this.connectResolve = null;
      this.connectReject = null;
      this.connectRequestId = null;
      if (this.connectTimeoutTimer !== null) {
        window.clearTimeout(this.connectTimeoutTimer);
        this.connectTimeoutTimer = null;
      }
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
      const timeoutTimer = window.setTimeout(() => {
        this.pendingRequests.delete(requestId);
        reject(new Error(`Request '${method}' timed out after ${REQUEST_TIMEOUT_MS / 1000}s.`));
      }, REQUEST_TIMEOUT_MS);
      this.pendingRequests.set(requestId, {
        resolve: (payload) => {
          window.clearTimeout(timeoutTimer);
          resolve(payload as T);
        },
        reject: (error) => {
          window.clearTimeout(timeoutTimer);
          reject(error);
        },
      });
      try {
        this.sendFrame({
          type: 'req',
          id: requestId,
          method,
          params,
        });
      } catch (error) {
        window.clearTimeout(timeoutTimer);
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
      return;
    }

    if (frame.event === 'profile.changed') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const profile = normalizePatProfile(payload.profile);
      const change = normalizeProfileChangelogItem(payload.change);
      if (profile) {
        useAppStore.getState().setPatProfile(profile);
      }
      if (change) {
        useAppStore.getState().prependProfileChangelogItem(change);
      }
      return;
    }

    if (frame.event === 'memory.changed') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      // Any memory change can affect the pending-drafts list (approve removes one,
      // discard removes one, a fresh proposal adds one) — resync it.
      void this.refreshMemoryDrafts();
      const item = normalizeMemoryItem(payload.item);
      if (item) {
        const store = useAppStore.getState();
        store.upsertMemoryItem(item);
        store.setLastMemoryChange({
          item,
          reason: payload.reason ? String(payload.reason) : 'upsert',
          sessionKey: payload.sessionKey ? String(payload.sessionKey) : null,
          runId: payload.runId ? String(payload.runId) : null,
        });
      }
      return;
    }

    if (frame.event === 'briefing.ready') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      useAppStore.getState().setReturnBriefing(normalizeReturnBriefing(payload.briefing));
      return;
    }

    if (frame.event === 'sessions.merge.updated') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const sessionKey = payload.sessionKey ? String(payload.sessionKey) : '';
      const mergeState = normalizeMergeState(payload.mergeState);
      if (sessionKey && mergeState) {
        useAppStore.getState().setMergeState(sessionKey, mergeState);
      }
      if (sessionKey && payload.message) {
        const message = normalizeMessage(
          payload.message as PublicMessagePayload,
          sessionKey,
          `merge-brief-${sessionKey}-${(payload.message as PublicMessagePayload).runId || 'final'}`,
          'assistant',
          'final',
          false,
        );
        useAppStore.getState().addMessage(sessionKey, message);
      }
      return;
    }

    if (frame.event === 'pulse.updated') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const pulse = normalizePulse(payload.pulse);
      if (pulse) {
        useAppStore.getState().upsertPulse(pulse);
      }
      return;
    }

    if (frame.event === 'messaging.updated') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const config = normalizeMessagingConfig(payload.config);
      const store = useAppStore.getState();
      if (config) {
        store.setMessagingConfig(config);
        store.setDestinations(config.destinations);
        return;
      }
      if (Array.isArray(payload.routes)) {
        const current = store.messagingConfig;
        if (current) {
          store.setMessagingConfig({
            ...current,
            routes: payload.routes.map(normalizeTelegramRoute).filter((item): item is TelegramSessionRoute => item != null),
          });
        }
      }
    }

    if (frame.event === 'approval.pending') {
      const payload = (frame.payload || {}) as Record<string, unknown>;
      const approval = normalizeApprovalRequest(payload.approval);
      if (approval) {
        const store = useAppStore.getState();
        store.setPendingApproval(approval);
        store.setRunPausedReason('awaiting_approval');
        store.upsertApprovalInHistory(approval);
      }
      return;
    }

    if (frame.event === 'approval.resolved') {
      const store = useAppStore.getState();
      store.setPendingApproval(null);
      store.setRunPausedReason(null);
      return;
    }
  }

  private handleResponseFrame(frame: ResponseFrame) {
    if (frame.id === this.connectRequestId) {
      if (frame.ok) {
        if (this.connectTimeoutTimer !== null) {
          window.clearTimeout(this.connectTimeoutTimer);
          this.connectTimeoutTimer = null;
        }
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
        if (this.connectTimeoutTimer !== null) {
          window.clearTimeout(this.connectTimeoutTimer);
          this.connectTimeoutTimer = null;
        }
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

  private async bootstrap() {
    try {
      const [providersPayload, toolsPayload, promptsPayload, sessionsPayload, profilePayload, personaPayload, personaSettingsPayload, identityPayload, memoryPayload, changelogPayload, briefingPayload, runtimeContextPayload, pulsePayload, messagingPayload, approvalsPayload] = await Promise.all([
        this.request<{ providers: unknown[] }>('providers.list', {}),
        this.request<{ tools: unknown[] }>('tools.list', {}),
        this.request<{ profiles?: unknown[]; taskModes?: unknown[] }>('prompts.list', {}),
        this.request<{ sessions: unknown[] }>('sessions.list', { includeArchived: useAppStore.getState().showArchived }),
        this.request<{ profile?: unknown | null }>('profile.get', {}),
        this.request<{ persona?: unknown | null }>('persona.get', {}),
        this.request<{ settings?: unknown | null }>('persona.settings.get', {}),
        this.request<{ identityContext?: unknown | null }>('identity.context', {}),
        this.request<{ items?: unknown[] }>('memory.list', { limit: 24 }),
        this.request<{ changelog?: unknown[] }>('profile.changelog', { limit: 20 }),
        this.request<{ briefing?: unknown | null }>('briefing.get', {}),
        this.request<{ runtimeContext?: unknown | null }>('runtime.context', {}),
        this.request<{ pulses?: unknown[] }>('pulse.list', {}),
        this.request<{ config?: unknown | null }>('messaging.config.get', {}),
        this.request<{ approvals?: unknown[] }>('approvals.list', {}),
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
      store.setPatProfile(normalizePatProfile(profilePayload.profile));
      store.setPersonaHome(normalizePersonaHome(personaPayload.persona));
      store.setPersonaSettings(normalizePersonaSettings(personaSettingsPayload.settings));
      store.setIdentityContext(normalizeIdentityContext(identityPayload.identityContext));
      store.setMemoryItems(
        Array.isArray(memoryPayload.items)
          ? memoryPayload.items.map(normalizeMemoryItem).filter((item): item is MemoryItem => item != null)
          : [],
      );
      void this.refreshMemoryDrafts();
      store.setProfileChangelog(
        Array.isArray(changelogPayload.changelog)
          ? changelogPayload.changelog
              .map(normalizeProfileChangelogItem)
              .filter((item): item is ProfileChangelogItem => item != null)
          : [],
      );
      store.setReturnBriefing(normalizeReturnBriefing(briefingPayload.briefing));
      store.setRuntimeContext(normalizeRuntimeContext(runtimeContextPayload.runtimeContext));
      store.setPulses(Array.isArray(pulsePayload.pulses) ? pulsePayload.pulses.map(normalizePulse).filter((item): item is PulseRecord => item != null) : []);
      const messagingConfig = normalizeMessagingConfig(messagingPayload.config);
      if (messagingConfig) {
        store.setMessagingConfig(messagingConfig);
        store.setDestinations(messagingConfig.destinations);
      }
      // Recover any approval still awaiting a decision (approval.pending is a
      // one-shot push, so a reload/reconnect mid-approval would otherwise lose
      // the card while the run stays parked on the backend).
      const pendingApprovals = Array.isArray(approvalsPayload.approvals)
        ? approvalsPayload.approvals.map(normalizeApprovalRequest).filter((item): item is ApprovalRequest => item != null)
        : [];
      const recoveredApproval = pendingApprovals[0] || null;
      if (recoveredApproval) {
        store.setPendingApproval(recoveredApproval);
        store.setRunPausedReason('awaiting_approval');
        store.upsertApprovalInHistory(recoveredApproval);
      }
      ensureDraftDefaultsAction();

      const currentKey = store.activeSessionKey;
      const hasCurrent = currentKey && sessions.some((session) => session.key === currentKey);
      const nextKey = hasCurrent ? currentKey : store.draftOpen ? null : sessions[0]?.key || null;
      store.setActiveSessionKey(nextKey);
      if (nextKey) {
        store.setDraftOpen(false);
        await this.loadHistory(nextKey);
      }
      // Phase 4.6: reconcile any runs that were in-flight when the socket dropped.
      await this.reconcilePendingRuns(sessions);
    } catch (error) {
      useAppStore.getState().setAppError(error instanceof Error ? error.message : 'Bootstrap failed.');
    }
  }

  /**
   * After a reconnect, reconcile pending assistant messages against server state.
   * A run that finished while we were disconnected is finalized from persisted
   * history; one still in-flight stays marked "reconnecting" (its session's
   * inFlightRunId still points at it) and keeps streaming once events resume.
   * Per HARNESS_REBUILD_V2 Phase 4.6.
   */
  private async reconcilePendingRuns(sessions: Session[]) {
    const store = useAppStore.getState();
    const pending = store.pendingAssistants;
    const pendingRunIds = Object.keys(pending);
    if (pendingRunIds.length === 0) return;
    const inFlightByRun = new Set(
      sessions.map((s) => s.inFlightRunId).filter((id): id is string => Boolean(id)),
    );
    for (const runId of pendingRunIds) {
      const target = pending[runId];
      if (inFlightByRun.has(runId)) {
        // Still running server-side — keep the reconnecting marker; events resume.
        store.updateMessage(target.sessionKey, target.localId, { reconnecting: true });
        continue;
      }
      // Run is no longer in-flight: it completed (or aborted) while we were away.
      // Re-load the session history so the persisted assistant message replaces
      // the optimistic pending one, then drop the pending tracker.
      try {
        await this.loadHistory(target.sessionKey);
      } catch {
        // best-effort; leave the message as-is if history reload fails
      }
      store.updateMessage(target.sessionKey, target.localId, { reconnecting: false });
      store.clearPendingAssistant(runId);
      if (store.activeRunId === runId) {
        store.setActiveRunId(null);
      }
    }
  }

  async refreshSessions() {
    return refreshSessionsAction(this.request.bind(this));
  }

  async loadModels(providerId: string): Promise<Model[]> {
    return loadModelsAction(this.request.bind(this), this.modelLoads, providerId);
  }

  async loadHistory(sessionKey: string) {
    return loadHistoryAction(this.request.bind(this), sessionKey);
  }

  async browseWorkspaceRoot(): Promise<{ workspaceRoot: string | null; runtimeContext: RuntimeContext | null }> {
    return browseWorkspaceRootRpc(this.request.bind(this));
  }

  async setWorkspaceRoot(workspaceRoot: string): Promise<RuntimeContext> {
    return setWorkspaceRootRpc(this.request.bind(this), workspaceRoot);
  }

  beginDraft() {
    beginDraftAction();
  }

  async renameSession(key: string, title: string) {
    return renameSessionAction(this.request.bind(this), key, title);
  }

  async archiveSession(key: string, archived: boolean) {
    return archiveSessionAction(this.request.bind(this), () => this.refreshSessions(), key, archived);
  }

  async debugCopySession(key: string): Promise<Session> {
    return debugCopySessionAction(
      this.request.bind(this),
      () => this.refreshSessions(),
      (sessionKey) => this.loadHistory(sessionKey),
      key,
    );
  }

  async createMergedSession(params: {
    sourceSessionKeys: string[];
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
    workspaceRoot: string;
    title?: string;
  }): Promise<{ session: Session; mergeState: SessionMergeState | null }> {
    return createMergedSessionRpc(this.request.bind(this), params);
  }

  async fetchApod(opts?: { date?: string; refresh?: boolean }): Promise<ApodResult> {
    return fetchApodRpc(this.request.bind(this), opts);
  }

  async listPulses(): Promise<PulseRecord[]> {
    return listPulsesRpc(this.request.bind(this));
  }

  async getMessagingConfig(): Promise<MessagingConfig | null> {
    return getMessagingConfigRpc(this.request.bind(this));
  }

  async listMessagingDestinations(): Promise<MessageDestination[]> {
    return listMessagingDestinationsRpc(this.request.bind(this));
  }

  async listMessagingRoutes(): Promise<TelegramSessionRoute[]> {
    return listMessagingRoutesRpc(this.request.bind(this));
  }

  async updateMessagingApprovalPolicy(params: {
    requireApprovalByDefault: boolean;
    hardlineBlocklist?: string[];
  }): Promise<MessagingConfig | null> {
    return updateMessagingApprovalPolicyRpc(this.request.bind(this), params);
  }

  async updateTelegramRuntimeDefaults(params: {
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
  }): Promise<MessagingConfig | null> {
    return updateTelegramRuntimeDefaultsRpc(this.request.bind(this), params);
  }

  async testMessagingPlatform(platform = 'telegram'): Promise<{
    config: MessagingConfig | null;
    result: {
      ok: boolean;
      connectionStatus: 'connected' | 'disconnected' | 'error' | 'unconfigured';
      message: string;
      verifiedAt: string | null;
    };
  }> {
    return testMessagingPlatformRpc(this.request.bind(this), platform);
  }

  async upsertMessagingDestination(destination: {
    id?: string;
    platform: string;
    target: string;
    displayName: string;
    threadLabel?: string | null;
    isDefault: boolean;
    requiresApproval: boolean;
    status?: 'configured' | 'unconfigured' | 'error';
  }): Promise<{ destination: MessageDestination | null; config: MessagingConfig | null }> {
    return upsertMessagingDestinationRpc(this.request.bind(this), destination);
  }

  async deleteMessagingDestination(destinationId: string): Promise<{ deleted: boolean; config: MessagingConfig | null }> {
    return deleteMessagingDestinationRpc(this.request.bind(this), destinationId);
  }

  async upsertMessagingRoute(route: {
    id?: string;
    platform: string;
    chatId: string;
    threadId?: string | null;
    sessionKey: string;
    titleOverride?: string | null;
  }): Promise<{ route: TelegramSessionRoute | null; routes: TelegramSessionRoute[] }> {
    return upsertMessagingRouteRpc(this.request.bind(this), route);
  }

  async deleteMessagingRoute(routeId: string): Promise<{ deleted: boolean; routes: TelegramSessionRoute[] }> {
    return deleteMessagingRouteRpc(this.request.bind(this), routeId);
  }

  async createPulseFromSession(params: {
    sessionKey: string;
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
  }): Promise<PulseRecord> {
    return createPulseFromSessionRpc(this.request.bind(this), params);
  }

  async dismissPulse(pulseId: string): Promise<PulseRecord> {
    return dismissPulseRpc(this.request.bind(this), pulseId);
  }

  async savePulses(params: {
    pulseIds: string[];
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
    workspaceRoot: string;
  }): Promise<{ session: Session; mergeState: SessionMergeState | null }> {
    return savePulsesRpc(this.request.bind(this), params);
  }

  async exportSession(key: string): Promise<SessionExportPayload> {
    return exportSessionRpc(this.request.bind(this), key);
  }

  async listSessionRuns(key: string, limit = 20): Promise<SessionRunRecord[]> {
    return listSessionRunsRpc(this.request.bind(this), key, limit);
  }

  async upsertMemory(input: {
    id?: string | null;
    category: MemoryItem['category'];
    title: string;
    summary: string;
    detail?: string | null;
    tags?: string[];
  }): Promise<MemoryItem | null> {
    return upsertMemoryRpc(this.request.bind(this), input);
  }

  async archiveMemory(id: string, archived = true): Promise<MemoryItem | null> {
    return archiveMemoryRpc(this.request.bind(this), id, archived);
  }

  /** Commit a model-proposed memory draft (optionally with operator edits). */
  async approveMemory(id: string, edits?: { category?: MemoryItem['category']; title?: string; summary?: string; detail?: string | null }): Promise<MemoryItem | null> {
    return approveMemoryRpc(this.request.bind(this), id, edits);
  }

  /** Discard a model-proposed memory draft outright. */
  async discardMemory(id: string): Promise<boolean> {
    return discardMemoryRpc(this.request.bind(this), id);
  }

  /** Refresh the pending (draft) memory list into the store. */
  async refreshMemoryDrafts(): Promise<void> {
    return refreshMemoryDraftsRpc(this.request.bind(this));
  }

  async updatePersonaSettings(settings: PersonaSettings): Promise<PersonaSettings | null> {
    return updatePersonaSettingsRpc(this.request.bind(this), settings);
  }

  /** List personas, marking the one resolved for the given runtime (override-honest). */
  async listPersonas(runtime?: { provider?: string | null; model?: string | null }): Promise<PersonaListItem[]> {
    return listPersonasRpc(this.request.bind(this), runtime);
  }

  /** Create a new persona scaffold. */
  async createPersona(personaId: string, displayName?: string): Promise<PersonaListItem | null> {
    return createPersonaRpc(this.request.bind(this), personaId, displayName);
  }

  /** Activate a persona for the current runtime (repoints a per-model override if present). */
  async selectPersona(personaId: string, runtime?: { provider?: string | null; model?: string | null }): Promise<PersonaSettings | null> {
    return selectPersonaRpc(this.request.bind(this), personaId, runtime);
  }

  async getPersonaSummary(options?: {
    provider?: string | null;
    model?: string | null;
    privacyTier?: string | null;
  }): Promise<PersonaHomeSummary | null> {
    return getPersonaSummaryRpc(this.request.bind(this), options);
  }

  async getPersonaContext(options?: {
    provider?: string | null;
    model?: string | null;
    privacyTier?: string | null;
    query?: string | null;
  }): Promise<PersonaContextPayload | null> {
    return getPersonaContextRpc(this.request.bind(this), options);
  }

  async draftPersonaFlavor(options: {
    provider: string;
    model?: string | null;
  }): Promise<PersonaFlavorDraft | null> {
    return draftPersonaFlavorRpc(this.request.bind(this), options);
  }

  async savePersonaFlavor(options: { provider: string; model?: string; draft: Record<string, unknown> }): Promise<PersonaHomeSummary | null> {
    return savePersonaFlavorRpc(this.request.bind(this), options);
  }

  async listSessionArtifacts(key: string, limit = 50): Promise<SessionArtifactRecord[]> {
    return listSessionArtifactsRpc(this.request.bind(this), key, limit);
  }

  /** Undo a model's file write/edit by restoring the recorded pre-edit content. */
  async revertEdit(key: string, path: string, afterDigest: string): Promise<{ ok: boolean; error?: string; path?: string; newDigest?: string }> {
    return revertEditRpc(this.request.bind(this), key, path, afterDigest);
  }

  /** Record an operator's decision on a pending high-risk tool approval; wakes the parked run.
   *  `approved_always` also persists the command to the global allowlist (Brick E). */
  async decideApproval(approvalId: string, decision: 'approved' | 'approved_always' | 'rejected', note?: string): Promise<{ ok: boolean; error?: string }> {
    return decideApprovalAction(this.request.bind(this), approvalId, decision, note);
  }

  /** Global shell allowlist (Access & Permissions — Brick F): the operator's standing approvals. */
  async listShellAllowlist(): Promise<ShellAllowlistEntry[]> {
    return listShellAllowlistRpc(this.request.bind(this));
  }

  async addShellAllowlist(command: string): Promise<ShellAllowlistEntry[]> {
    return addShellAllowlistRpc(this.request.bind(this), command);
  }

  async removeShellAllowlist(command: string): Promise<ShellAllowlistEntry[]> {
    return removeShellAllowlistRpc(this.request.bind(this), command);
  }

  /** List viewable files under a session's workspace root (read-only file viewer). */
  async listWorkspaceFiles(key: string): Promise<{ root: string; files: WorkspaceFile[] }> {
    return listWorkspaceFilesRpc(this.request.bind(this), key);
  }

  /** Read one file under a session's workspace root, rendered by the file viewer. */
  async readWorkspaceFile(key: string, path: string): Promise<WorkspaceFileContent> {
    return readWorkspaceFileRpc(this.request.bind(this), key, path);
  }

  /** Operator inline-edit: write a file under a session's workspace root (revertible). */
  async writeWorkspaceFile(key: string, path: string, content: string): Promise<WorkspaceFileContent & { digest: string; revertible: boolean }> {
    return writeWorkspaceFileRpc(this.request.bind(this), key, path, content);
  }

  /** Read one persona file (scoped to the persona root) for the inline editor. */
  async readPersonaFile(path: string): Promise<WorkspaceFileContent> {
    return readPersonaFileRpc(this.request.bind(this), path);
  }

  /** Operator inline-edit: write a persona file (scoped to the persona root, revertible). */
  async writePersonaFile(path: string, content: string): Promise<WorkspaceFileContent & { digest: string; revertible: boolean }> {
    return writePersonaFileRpc(this.request.bind(this), path, content);
  }

  async resolveSessionRun(key: string, runId: string): Promise<SessionRunRecord | null> {
    return resolveSessionRunRpc(this.request.bind(this), key, runId);
  }

  async resolveSessionState(key: string): Promise<SessionStateRecord | null> {
    return resolveSessionStateRpc(this.request.bind(this), key);
  }

  async resolveMergeState(key: string): Promise<SessionMergeState | null> {
    return resolveMergeStateRpc(this.request.bind(this), key);
  }

  async optimizePrompt(options: {
    prompt: string;
    provider?: string;
    model?: string;
    customTransform?: string;
  }): Promise<PromptOptimizationResult> {
    return optimizePromptRpc(this.request.bind(this), options);
  }

  async sendMessage(message: string) {
    const trimmed = message.trim();
    if (!trimmed) return;

    const store = useAppStore.getState();
    store.clearAppError();

    try {
      let session = store.sessions.find((item) => item.key === store.activeSessionKey) || null;
      if (!session) {
        const draft = store.draftSettings;
        const createPayload = await this.request<{ session: unknown }>('sessions.create', {
          provider: draft.provider,
          model: draft.model || undefined,
          systemPromptId: draft.systemPromptId || undefined,
          taskPromptId: draft.taskPromptId || undefined,
          personaId: draft.personaId || undefined,
          personaFlavorId: draft.personaFlavorId || undefined,
          personaPrivacyTier: draft.personaPrivacyTier || undefined,
          workspaceRoot: draft.workspaceRoot || undefined,
          starterIntentId: store.draftStarterIntent?.id || undefined,
        });
        session = normalizeSession(createPayload.session);
        store.upsertSession(session);
        store.setActiveSessionKey(session.key);
        store.setDraftOpen(false);
        store.setDraftStarterIntent(null);
      }

      // Mid-session runtime mutability (A + B1): a locked session may carry a pending
      // model / Access override. Apply it on this send; the backend reconciles the
      // binding, then refreshSessions pulls the canonical values and we clear it.
      const override = store.sessionRuntimeOverrides[session.key];
      const effectiveModel = override?.model || session.model;
      const effectiveTaskPromptId = override?.taskPromptId ?? session.taskPromptId;

      const userMessage: Message = {
        localId: makeLocalId('user'),
        sessionKey: session.key,
        runId: null,
        role: 'user',
        content: trimmed,
        timestamp: new Date().toISOString(),
        provider: session.provider,
        model: effectiveModel,
        providerSessionId: session.providerSessionId,
        state: 'final',
        toolExecution: null,
        errorMessage: null,
        optimistic: true,
      };
      store.addMessage(session.key, userMessage);

      const payload = await this.request<{ runId?: string; status?: string }>('chat.send', {
        sessionKey: session.key,
        message: trimmed,
        provider: session.provider,
        model: effectiveModel || undefined,
        systemPromptId: session.systemPromptId || undefined,
        taskPromptId: effectiveTaskPromptId || undefined,
        personaId: session.personaId || undefined,
        personaFlavorId: session.personaFlavorId || undefined,
        personaPrivacyTier: session.personaPrivacyTier || undefined,
      });
      store.clearSessionRuntimeOverride(session.key);
      const runId = payload.runId ? String(payload.runId) : null;
      const status = payload.status ? String(payload.status) : '';

      if (status === 'in_flight') {
        throw new Error('This session already has a reply in progress.');
      }

      if (runId) {
        // Clear live tool calls and turn state from the previous run.
        store.clearLiveToolCalls();
        store.setLastTurnState(null);

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
      const errorMessage = error instanceof Error ? error.message : 'Unable to send message.';
      const targetSessionKey = store.activeSessionKey || DRAFT_TRANSCRIPT_SESSION_KEY;
      store.setAppError(errorMessage);
      store.addMessage(targetSessionKey, {
        localId: makeLocalId('system'),
        sessionKey: targetSessionKey,
        runId: null,
        role: 'system',
        content: errorMessage,
        timestamp: new Date().toISOString(),
        provider: null,
        model: null,
        providerSessionId: null,
        state: 'error',
        toolExecution: null,
        errorMessage,
        optimistic: false,
      });
      throw error;
    }
  }

  async abortActiveRun() {
    return abortActiveRunAction(this.request.bind(this));
  }

  // ---------------------------------------------------------------------------
  // Provider auth RPCs
  // ---------------------------------------------------------------------------

  async providerAuthStatus(providerId: string): Promise<ProviderAuthStatus> {
    return providerAuthStatusRpc(this.request.bind(this), providerId);
  }

  async providerAuthBeginLogin(providerId: string, redirectUri?: string): Promise<{ loginId: string; authorizeUrl: string; redirectUri: string; state: string }> {
    return providerAuthBeginLoginRpc(this.request.bind(this), providerId, redirectUri);
  }

  async providerAuthLogout(providerId: string): Promise<ProviderAuthStatus> {
    return providerAuthLogoutRpc(this.request.bind(this), providerId);
  }

  private handleChatEvent(payload: ChatEventPayload) {
    const store = useAppStore.getState();
    const runId = payload.runId ? String(payload.runId) : null;
    const sessionKey = payload.sessionKey;
    const toolExecution = normalizeToolExecution(payload.toolExecution);

    if (payload.state === 'reasoning_delta') {
      // Phase 4: native reasoning-summary deltas render as inline "thinking"
      // narration between tool calls (Claude Code-style).
      const text = typeof payload.text === 'string' ? payload.text : '';
      const target = runId ? store.pendingAssistants[runId] : undefined;
      if (target && text) {
        store.appendMessagePart(target.sessionKey, target.localId, { kind: 'thinking', text });
      }
      return;
    }

    if (payload.state === 'tool_called') {
      const rawToolCall = payload.toolCall as Record<string, unknown> | null | undefined;
      if (rawToolCall && runId) {
        const toolId = String(rawToolCall.toolId ?? rawToolCall.tool_id ?? 'tool');
        const liveId = String(rawToolCall.callId ?? rawToolCall.call_id ?? `${runId}:${rawToolCall.step ?? store.liveToolCalls.length}:${toolId}`);
        store.pushLiveToolCall({
          id: liveId,
          toolId,
          state: 'running',
          summary: `Calling ${toolId}`,
          error: null,
          startedAt: new Date().toISOString(),
          completedAt: null,
        });
        const target = store.pendingAssistants[runId];
        if (target) {
          const callId = String(rawToolCall.callId ?? rawToolCall.call_id ?? `${runId}:${rawToolCall.step ?? store.liveToolCalls.length}:${rawToolCall.toolId ?? rawToolCall.tool_id ?? 'tool'}`);
          const hint = rawToolCall.hint
            ? String(rawToolCall.hint)
            : rawToolCall.arguments && typeof rawToolCall.arguments === 'object'
              ? JSON.stringify(rawToolCall.arguments)
              : null;
          store.appendMessagePart(target.sessionKey, target.localId, {
            kind: 'tool_call',
            callId,
            toolId,
            turnId: rawToolCall.turnId ? String(rawToolCall.turnId) : null,
            decisionId: rawToolCall.decisionId ? String(rawToolCall.decisionId) : null,
            hint,
            target: rawToolCall.target ? String(rawToolCall.target) : hint,
            at: new Date().toISOString(),
          });
        }
      }
      return;
    }

    if (payload.state === 'tool_result') {
      if (toolExecution && runId) {
        const existingMatch = [...store.liveToolCalls]
          .reverse()
          .find((call) => call.state === 'running' && call.toolId === toolExecution.toolId);
        store.pushLiveToolCall({
          id: existingMatch?.id || toolExecution.callId || `${runId}:${toolExecution.toolId}:${store.liveToolCalls.length}`,
          toolId: toolExecution.toolId,
          state: toolExecution.ok
            ? 'success'
            : toolExecution.summary?.toLowerCase().includes('blocked') || toolExecution.channel === 'policy'
              ? 'blocked'
              : 'failed',
          summary: toolExecution.summary,
          error: toolExecution.error ?? null,
          startedAt: existingMatch?.startedAt || new Date().toISOString(),
          completedAt: new Date().toISOString(),
        });

        const target = store.pendingAssistants[runId];
        if (target) {
          const toolPayloadRecord = payload.toolExecution as unknown as Record<string, unknown> | null | undefined;
          const batchMembers = Array.isArray(toolPayloadRecord?.members) ? toolPayloadRecord?.members : [];
          if (Array.isArray(batchMembers) && batchMembers.length > 1) {
            store.appendMessagePart(target.sessionKey, target.localId, {
              kind: 'tool_batch',
              batchId: `batch-${runId}`,
              label: buildBatchLabel(String(batchMembers[0] && typeof batchMembers[0] === 'object' ? (batchMembers[0] as Record<string, unknown>).toolId || toolExecution.toolId : toolExecution.toolId), batchMembers.length),
              members: batchMembers.map((m: unknown) => {
                const mb = (m || {}) as Record<string, unknown>;
                return {
                  callId: String(mb.callId ?? ''),
                  toolId: String(mb.toolId ?? toolExecution.toolId),
                  turnId: mb.turnId ? String(mb.turnId) : toolExecution.turnId || null,
                  decisionId: mb.decisionId ? String(mb.decisionId) : toolExecution.decisionId || null,
                  ok: Boolean(mb.ok),
                  summary: String(mb.summary ?? ''),
                  error: mb.error ? String(mb.error) : null,
                  artifactId: mb.artifactId ? String(mb.artifactId) : null,
                  target: mb.target ? String(mb.target) : null,
                  workspaceRoot: mb.workspaceRoot ? String(mb.workspaceRoot) : null,
                  scope: mb.scope === 'outside_workspace' ? 'outside_workspace' : mb.scope === 'inside_workspace' ? 'inside_workspace' : null,
                  accessAction: mb.accessAction === 'read' || mb.accessAction === 'write' || mb.accessAction === 'unknown' ? mb.accessAction : null,
                  policyDecision:
                    mb.policyDecision === 'allowed' ||
                    mb.policyDecision === 'read_roam' ||
                    mb.policyDecision === 'write_blocked' ||
                    mb.policyDecision === 'approval_required' ||
                    mb.policyDecision === 'unsafe_unknown'
                      ? mb.policyDecision
                      : null,
                  policySummary: mb.policySummary ? String(mb.policySummary) : null,
                  preview: normalizeToolResultPreview(mb.preview),
                  effect: normalizeToolEffect(mb.effect),
                };
              }),
              ok: toolExecution.ok,
              workspaceRoot: toolPayloadRecord?.workspaceRoot ? String(toolPayloadRecord.workspaceRoot) : toolExecution.workspaceRoot || null,
              at: new Date().toISOString(),
            });
          } else {
            store.appendMessagePart(target.sessionKey, target.localId, {
              kind: 'tool_result',
              callId: toolExecution.callId || '',
              toolId: toolExecution.toolId,
              turnId: toolExecution.turnId || null,
              decisionId: toolExecution.decisionId || null,
              ok: toolExecution.ok,
              summary: toolExecution.summary,
              error: toolExecution.error ?? null,
              artifactId: toolExecution.artifactId || null,
              target: toolExecution.target || null,
              workspaceRoot: toolExecution.workspaceRoot || null,
              scope: toolExecution.scope || null,
              accessAction: toolExecution.accessAction || null,
              policyDecision: toolExecution.policyDecision || null,
              policySummary: toolExecution.policySummary || null,
              preview: normalizeToolResultPreview(toolPayloadRecord?.preview),
              effect: toolExecution.effect || null,
              at: new Date().toISOString(),
            });
          }
        }
      }
      return;
    }

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
          parts: normalizeMessageParts(payload.message?.parts),
          errorMessage: null,
          optimistic: true,
        });
        store.registerPendingAssistant(runId, sessionKey, localId);
        target = { sessionKey, localId };
      }

      if (target) {
        const existing = useAppStore.getState().messages[target.sessionKey]?.find((message) => message.localId === target.localId);
        const chunk = payload.message?.content ? String(payload.message.content) : '';
        const normalizedParts = normalizeMessageParts(payload.message?.parts);
        store.updateMessage(target.sessionKey, target.localId, {
          content: `${existing?.content || ''}${chunk}`,
          provider: payload.provider ? String(payload.provider) : existing?.provider || null,
          model: payload.model ? String(payload.model) : existing?.model || null,
          state: 'delta',
          toolExecution: toolExecution || existing?.toolExecution || null,
          parts: normalizedParts || existing?.parts || null,
          optimistic: true,
        });
        if (!normalizedParts && chunk && existing?.parts != null) {
          store.appendMessagePart(target.sessionKey, target.localId, { kind: 'text', content: chunk });
        }
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
              ? normalizeAssistantDisplayText(payload.message.content)
              : existing?.content || '',
          provider: payload.provider ? String(payload.provider) : existing?.provider || null,
          model: payload.model ? String(payload.model) : existing?.model || null,
          state: payload.state,
          toolExecution: toolExecution || existing?.toolExecution || null,
          parts: normalizeMessageParts(payload.message?.parts) || existing?.parts || null,
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

      // Capture turnState snapshot from final event before clearing live calls.
      if (payload.state === 'final') {
        const ts = (payload as unknown as Record<string, unknown>).turnState;
        if (ts && typeof ts === 'object') {
          const t = ts as Record<string, unknown>;
          const snapshot: TurnStateSnapshot = {
            turnId: t.turnId ? String(t.turnId) : null,
            decisionId: t.decisionId ? String(t.decisionId) : null,
            toolCallCount: Number(t.toolCallCount ?? 0),
            visitedTools: Array.isArray(t.visitedTools) ? (t.visitedTools as string[]) : [],
            visitedPaths: Array.isArray(t.visitedPaths) ? (t.visitedPaths as string[]) : [],
            groundingActions: Array.isArray(t.groundingActions) ? (t.groundingActions as string[]) : [],
            failedActions: Array.isArray(t.failedActions)
              ? (t.failedActions as Array<{ toolId: string; summary: string; error: string | null }>)
              : [],
            openQuestions: Array.isArray(t.openQuestions) ? (t.openQuestions as string[]) : [],
            lastToolResultSummary: String(t.lastToolResultSummary ?? ''),
            terminalReason: t.terminalReason != null ? String(t.terminalReason) : null,
            transitionReason: String(t.transitionReason ?? 'completed'),
          };
          store.setLastTurnState(snapshot);
        }
        const identityContext = normalizeIdentityContextRuntime((payload as unknown as Record<string, unknown>).identityContext);
        if (identityContext) {
          store.setSessionIdentityUsage(sessionKey, identityContext);
        }
        // Don't clear liveToolCalls immediately — RunActivityPanel takes over after
        // a short delay when the activity data reloads.  Components that display
        // live calls should switch to the run record once it's available.
      }

      // Only close the draft if the completed run belongs to the currently active session.
      // Closing unconditionally would destroy a new draft the user opened while a prior run finished.
      if (sessionKey && store.activeSessionKey === sessionKey) {
        store.setDraftOpen(false);
      }
      void this.refreshSessions();
      // The run may have proposed a memory draft (memory.write) — surface it.
      void this.refreshMemoryDrafts();
    }
  }
}

export const wsClient = new WsClient();
