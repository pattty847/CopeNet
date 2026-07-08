import { useAppStore } from '../store/useAppStore';
import {
  ChatEventPayload,
  EventFrame,
  IncomingFrame,
  MemoryItem,
  UserNoteProposal,
  MessageDestination,
  MessagePart,
  MessagingConfig,
  Model,
  PersonaContextPayload,
  ApodResult,
  PersonaFlavorDraft,
  PersonaHomeSummary,
  PersonaListItem,
  PersonaSettings,
  ChatAttachment,
  PromptOptimizationResult,
  PulseRecord,
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
  WorkspaceFile,
  WorkspaceFileContent,
  ShellAllowlistEntry,
} from '../types/backend';
import {
  normalizeApprovalRequest,
  normalizeAssistantDisplayText,
  normalizeDestination,
  normalizeMemoryItem,
  normalizeMergeState,
  normalizeMessage,
  normalizeMessagingConfig,
  normalizePersonaContext,
  normalizePersonaFlavorDraft,
  normalizePulse,
  normalizeReturnBriefing,
  normalizeSession,
  normalizeTelegramRoute,
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
  approveUserNoteRpc,
  archiveMemoryRpc,
  createPersonaRpc,
  discardMemoryRpc,
  discardUserNoteRpc,
  draftPersonaFlavorRpc,
  getPersonaContextRpc,
  getPersonaSummaryRpc,
  listPersonasRpc,
  refreshMemoryDraftsRpc,
  refreshUserNoteDraftsRpc,
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
import { marketBriefGetRpc, marketBriefRunRpc, marketDashboardRpc, marketInterpretRpc, marketReadGetRpc, marketRefreshRpc, marketTickerEvidenceRpc, marketTickerRpc, marketUniverseRpc, marketWebullStatusRpc, marketWebullSyncRpc, marketBacktestRunRpc, marketBacktestStressTestRpc, marketWatchlistGetRpc, marketWatchlistAddRpc, marketWatchlistRemoveRpc, marketSymbolsSearchRpc } from './wsMarketRpc';
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
import { bootstrapAction } from './wsBootstrapAction';
import { loadModelsAction } from './wsCatalogActions';
import { abortActiveRunAction, decideApprovalAction, sendMessageAction } from './wsChatActions';
import { handleChatEventAction } from './wsChatEvents';
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
const REQUEST_TIMEOUT_MS = 45000;
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

    if (frame.event === 'userNotes.changed') {
      // approve/discard/new proposal all change the draft list — resync it.
      void this.refreshUserNoteDrafts();
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
    return bootstrapAction(
      this.request.bind(this),
      (sessionKey) => this.loadHistory(sessionKey),
      (sessions) => this.reconcilePendingRuns(sessions),
      () => { void this.refreshUserNoteDrafts(); return this.refreshMemoryDrafts(); },
    );
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

  async marketDashboard() {
    return marketDashboardRpc(this.request.bind(this));
  }

  async marketTicker(symbol: string) {
    return marketTickerRpc(this.request.bind(this), symbol);
  }

  async marketTickerEvidence(symbol: string, refresh = false) {
    return marketTickerEvidenceRpc(this.request.bind(this), symbol, refresh);
  }

  async marketUniverse() {
    return marketUniverseRpc(this.request.bind(this));
  }

  async marketRefresh(scope: 'all' | 'macro' | 'signals' | 'edgar' = 'all') {
    return marketRefreshRpc(this.request.bind(this), scope);
  }

  async marketInterpret(target: string = 'market') {
    return marketInterpretRpc(this.request.bind(this), target);
  }

  async marketReadGet(target: string = 'market') {
    return marketReadGetRpc(this.request.bind(this), target);
  }

  async marketBriefGet() {
    return marketBriefGetRpc(this.request.bind(this));
  }

  async marketBriefRun(force = true) {
    return marketBriefRunRpc(this.request.bind(this), force);
  }

  async marketWebullStatus() {
    return marketWebullStatusRpc(this.request.bind(this));
  }

  async marketWebullSync() {
    return marketWebullSyncRpc(this.request.bind(this));
  }

  async marketBacktestRun(params: {
    sessionKey: string;
    symbols: string[];
    weights: number[];
    startDate: string;
    endDate: string;
    benchmark?: string;
    rebalance?: string;
    rebalanceInterval?: string | null;
  }) {
    return marketBacktestRunRpc(this.request.bind(this), params);
  }

  async marketBacktestStressTest(params: {
    sessionKey: string;
    scenarioKey: string;
    positions: any[];
  }) {
    return marketBacktestStressTestRpc(this.request.bind(this), params);
  }

  async marketWatchlistGet() {
    return marketWatchlistGetRpc(this.request.bind(this));
  }

  async marketWatchlistAdd(symbol: string, name = '') {
    return marketWatchlistAddRpc(this.request.bind(this), symbol, name);
  }

  async marketWatchlistRemove(symbol: string) {
    return marketWatchlistRemoveRpc(this.request.bind(this), symbol);
  }

  async marketSymbolsSearch(query: string, limit = 8) {
    return marketSymbolsSearchRpc(this.request.bind(this), query, limit);
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

  /** Approve a model-proposed USER.md delta (merges it into USER.md). */
  async approveUserNote(id: string, edits?: { targetSection?: string; summary?: string; body?: string }): Promise<UserNoteProposal | null> {
    return approveUserNoteRpc(this.request.bind(this), id, edits);
  }

  /** Discard a model-proposed USER.md delta outright. */
  async discardUserNote(id: string): Promise<boolean> {
    return discardUserNoteRpc(this.request.bind(this), id);
  }

  /** Refresh the pending (draft) USER.md proposal list into the store. */
  async refreshUserNoteDrafts(): Promise<void> {
    return refreshUserNoteDraftsRpc(this.request.bind(this));
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

  async sendMessage(message: string, attachments?: ChatAttachment[]) {
    return sendMessageAction(this.request.bind(this), message, attachments);
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
    return handleChatEventAction(
      payload,
      () => this.refreshSessions(),
      () => { void this.refreshUserNoteDrafts(); return this.refreshMemoryDrafts(); },
    );

  }
}

export const wsClient = new WsClient();
