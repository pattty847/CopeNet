import { create } from 'zustand';
import { ApprovalOutcome, ApprovalRequest, DataToolsRoute, DraftSettings, LiveToolCall, MediaAsset, MediaAssetDetail, Message, MessageDestination, MessagingConfig, Model, PatProfile, ProfileChangelogItem, PromptOption, Provider, ProviderAuthStatus, ReturnBriefingPayload, RunTimeline, Session, ToolDescriptor, TurnStateSnapshot, WsStatus } from '../types/backend';
import type { InspectorTarget } from '../runtime/types';

export type AppSection = 'home' | 'agents' | 'workflows' | 'data-tools' | 'observability' | 'experiments';
export type ThemeMode = 'light' | 'dark';
export type RightPanelTab = 'inbox' | 'runtime' | 'artifacts' | 'activity' | 'approvals';
export type WorkflowsRoute = 'hub' | 'meme-lab';

interface AppState {
  wsStatus: WsStatus;
  authError: string | null;
  appError: string | null;
  activeRunId: string | null;
  setWsStatus: (status: WsStatus) => void;
  setAuthError: (message: string | null) => void;
  setAppError: (message: string | null) => void;
  clearAppError: () => void;
  setActiveRunId: (id: string | null) => void;
  currentSection: AppSection;
  setCurrentSection: (section: AppSection) => void;
  themeMode: ThemeMode;
  setThemeMode: (mode: ThemeMode) => void;
  toggleThemeMode: () => void;
  dataToolsRoute: DataToolsRoute;
  setDataToolsRoute: (route: DataToolsRoute) => void;
  workflowsRoute: WorkflowsRoute;
  setWorkflowsRoute: (route: WorkflowsRoute) => void;
  draftComposerSeed: string | null;
  setDraftComposerSeed: (seed: string | null) => void;
  memeLabSeedAsset: MediaAssetDetail | null;
  setMemeLabSeedAsset: (asset: MediaAssetDetail | null) => void;

  primaryNavCollapsed: boolean;
  setPrimaryNavCollapsed: (collapsed: boolean) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  mobileOverflowOpen: boolean;
  setMobileOverflowOpen: (open: boolean) => void;
  mobileSessionsOpen: boolean;
  setMobileSessionsOpen: (open: boolean) => void;
  mobileInspectorOpen: boolean;
  setMobileInspectorOpen: (open: boolean) => void;
  mobileMemeHistoryOpen: boolean;
  setMobileMemeHistoryOpen: (open: boolean) => void;
  mobileMemeKeepersOpen: boolean;
  setMobileMemeKeepersOpen: (open: boolean) => void;
  rightPanelOpen: boolean;
  setRightPanelOpen: (open: boolean) => void;
  commandPaletteOpen: boolean;
  setCommandPaletteOpen: (open: boolean) => void;
  rightPanelTab: RightPanelTab;
  setRightPanelTab: (tab: RightPanelTab) => void;
  inspectorTarget: InspectorTarget | null;
  setInspectorTarget: (target: InspectorTarget | null) => void;

  providers: Provider[];
  modelsByProvider: Record<string, Model[]>;
  loadedModelProviders: Record<string, boolean>;
  tools: ToolDescriptor[];
  profiles: PromptOption[];
  taskModes: PromptOption[];
  mediaAssets: MediaAsset[];
  mediaAssetsLoaded: boolean;
  mediaImporting: boolean;
  mediaImportError: string | null;
  mediaImportStatus: string | null;
  mediaImportProgress: number | null;
  setProviders: (providers: Provider[]) => void;
  setModelsForProvider: (providerId: string, models: Model[]) => void;
  setTools: (tools: ToolDescriptor[]) => void;
  setPromptCatalog: (profiles: PromptOption[], taskModes: PromptOption[]) => void;
  setMediaAssets: (assets: MediaAsset[]) => void;
  prependMediaAsset: (asset: MediaAsset) => void;
  setMediaAssetsLoaded: (loaded: boolean) => void;
  setMediaImporting: (importing: boolean) => void;
  setMediaImportError: (message: string | null) => void;
  setMediaImportStatus: (status: string | null) => void;
  setMediaImportProgress: (progress: number | null) => void;

  sessions: Session[];
  setSessions: (sessions: Session[]) => void;
  upsertSession: (session: Session) => void;
  activeSessionKey: string | null;
  setActiveSessionKey: (key: string | null) => void;
  draftOpen: boolean;
  setDraftOpen: (open: boolean) => void;
  showArchived: boolean;
  setShowArchived: (show: boolean) => void;
  draftSettings: DraftSettings;
  replaceDraftSettings: (settings: DraftSettings) => void;
  patchDraftSettings: (updates: Partial<DraftSettings>) => void;

  messages: Record<string, Message[]>;
  setMessages: (sessionKey: string, messages: Message[]) => void;
  addMessage: (sessionKey: string, message: Message) => void;
  updateMessage: (sessionKey: string, localId: string, updates: Partial<Message>) => void;
  pendingAssistants: Record<string, { sessionKey: string; localId: string }>;
  registerPendingAssistant: (runId: string, sessionKey: string, localId: string) => void;
  clearPendingAssistant: (runId: string) => void;

  // Approval subsystem
  pendingApproval: ApprovalRequest | null;
  runPausedReason: 'awaiting_approval' | null;
  approvalHistory: ApprovalRequest[];
  setPendingApproval: (req: ApprovalRequest | null) => void;
  resolveApproval: (approvalId: string, outcome: ApprovalOutcome) => void;
  setRunPausedReason: (reason: 'awaiting_approval' | null) => void;
  upsertApprovalInHistory: (req: ApprovalRequest) => void;
  loadApprovalHistory: (history: ApprovalRequest[]) => void;

  // Messaging destinations
  destinations: MessageDestination[];
  setDestinations: (destinations: MessageDestination[]) => void;

  // Messaging platform config
  messagingConfig: MessagingConfig | null;
  setMessagingConfig: (config: MessagingConfig) => void;

  // Run timeline (paused-run lifecycle view)
  runTimeline: RunTimeline | null;
  setRunTimeline: (timeline: RunTimeline | null) => void;

  // Send-message composer
  composerOpen: boolean;
  composerTarget: string | null;
  composerMessage: string;
  setComposerOpen: (open: boolean) => void;
  setComposerTarget: (target: string | null) => void;
  setComposerMessage: (message: string) => void;
  resetComposer: () => void;

  // Live tool execution (in-flight run streaming)
  // Populated from toolExecution payloads on delta events; cleared on run start/finish.
  liveToolCalls: LiveToolCall[];
  pushLiveToolCall: (call: LiveToolCall) => void;
  clearLiveToolCalls: () => void;

  // Last turn-state snapshot (populated from the final event's turnState payload)
  lastTurnState: TurnStateSnapshot | null;
  setLastTurnState: (snapshot: TurnStateSnapshot | null) => void;

  // Provider auth statuses (keyed by provider id, e.g. "openai-codex")
  providerAuthStatuses: Record<string, ProviderAuthStatus>;
  setProviderAuthStatus: (providerId: string, status: ProviderAuthStatus) => void;
  clearProviderAuthStatus: (providerId: string) => void;

  // Pat Profile (v1 — frontend shell, backend contract pending)
  // Null until the backend profile RPC ships and pushes a real profile.
  patProfile: PatProfile | null;
  setPatProfile: (profile: PatProfile | null) => void;

  // Return Briefing — "I'm back" re-entry payload
  // Null until the backend ships the briefing RPC or a dev trigger seeds it.
  returnBriefing: ReturnBriefingPayload | null;
  setReturnBriefing: (briefing: ReturnBriefingPayload | null) => void;
  dismissReturnBriefing: () => void;

  // Profile changelog — receipt-style history of profile mutations
  profileChangelog: ProfileChangelogItem[];
  setProfileChangelog: (changelog: ProfileChangelogItem[]) => void;
  prependProfileChangelogItem: (item: ProfileChangelogItem) => void;
}

function sortSessions(sessions: Session[]) {
  return [...sessions].sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')));
}

function upsertInHistory(history: ApprovalRequest[], req: ApprovalRequest): ApprovalRequest[] {
  const idx = history.findIndex((r) => r.approvalId === req.approvalId);
  if (idx >= 0) {
    const next = [...history];
    next[idx] = req;
    return next;
  }
  return [req, ...history];
}

const DEFAULT_DRAFT: DraftSettings = {
  provider: 'codex-cli',
  model: 'gpt-5.4',
  systemPromptId: 'default',
  taskPromptId: 'none',
};

export const useAppStore = create<AppState>((set) => ({
  wsStatus: 'disconnected',
  authError: null,
  appError: null,
  activeRunId: null,
  setWsStatus: (status) => set({ wsStatus: status }),
  setAuthError: (message) => set({ authError: message }),
  setAppError: (message) => set({ appError: message }),
  clearAppError: () => set({ appError: null }),
  setActiveRunId: (id) => set({ activeRunId: id }),
  currentSection: 'home',
  setCurrentSection: (section) => set({ currentSection: section }),
  themeMode: 'light',
  setThemeMode: (mode) => set({ themeMode: mode }),
  toggleThemeMode: () =>
    set((state) => ({
      themeMode: state.themeMode === 'light' ? 'dark' : 'light',
    })),
  dataToolsRoute: 'hub',
  setDataToolsRoute: (route) => set({ dataToolsRoute: route }),
  workflowsRoute: 'hub',
  setWorkflowsRoute: (route) => set({ workflowsRoute: route }),
  draftComposerSeed: null,
  setDraftComposerSeed: (seed) => set({ draftComposerSeed: seed }),
  memeLabSeedAsset: null,
  setMemeLabSeedAsset: (asset) => set({ memeLabSeedAsset: asset }),

  primaryNavCollapsed: false,
  setPrimaryNavCollapsed: (collapsed) => set({ primaryNavCollapsed: collapsed }),
  sidebarOpen: true,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  mobileOverflowOpen: false,
  setMobileOverflowOpen: (open) => set({ mobileOverflowOpen: open }),
  mobileSessionsOpen: false,
  setMobileSessionsOpen: (open) => set({ mobileSessionsOpen: open }),
  mobileInspectorOpen: false,
  setMobileInspectorOpen: (open) => set({ mobileInspectorOpen: open }),
  mobileMemeHistoryOpen: false,
  setMobileMemeHistoryOpen: (open) => set({ mobileMemeHistoryOpen: open }),
  mobileMemeKeepersOpen: false,
  setMobileMemeKeepersOpen: (open) => set({ mobileMemeKeepersOpen: open }),
  rightPanelOpen: true,
  setRightPanelOpen: (open) => set({ rightPanelOpen: open }),
  commandPaletteOpen: false,
  setCommandPaletteOpen: (open) => set({ commandPaletteOpen: open }),
  rightPanelTab: 'runtime',
  setRightPanelTab: (tab) => set({ rightPanelTab: tab }),
  inspectorTarget: null,
  setInspectorTarget: (target) => set({ inspectorTarget: target }),

  providers: [],
  modelsByProvider: {},
  loadedModelProviders: {},
  tools: [],
  profiles: [],
  taskModes: [],
  mediaAssets: [],
  mediaAssetsLoaded: false,
  mediaImporting: false,
  mediaImportError: null,
  mediaImportStatus: null,
  mediaImportProgress: null,
  setProviders: (providers) => set({ providers }),
  setModelsForProvider: (providerId, models) =>
    set((state) => ({
      modelsByProvider: { ...state.modelsByProvider, [providerId]: models },
      loadedModelProviders: { ...state.loadedModelProviders, [providerId]: true },
    })),
  setTools: (tools) => set({ tools }),
  setPromptCatalog: (profiles, taskModes) => set({ profiles, taskModes }),
  setMediaAssets: (assets) => set({ mediaAssets: assets }),
  prependMediaAsset: (asset) =>
    set((state) => ({
      mediaAssets: [asset, ...state.mediaAssets.filter((item) => item.assetId !== asset.assetId)],
    })),
  setMediaAssetsLoaded: (loaded) => set({ mediaAssetsLoaded: loaded }),
  setMediaImporting: (importing) => set({ mediaImporting: importing }),
  setMediaImportError: (message) => set({ mediaImportError: message }),
  setMediaImportStatus: (status) => set({ mediaImportStatus: status }),
  setMediaImportProgress: (progress) => set({ mediaImportProgress: progress }),

  sessions: [],
  setSessions: (sessions) => set({ sessions: sortSessions(sessions) }),
  upsertSession: (session) =>
    set((state) => {
      const next = state.sessions.filter((item) => item.key !== session.key);
      next.push(session);
      return { sessions: sortSessions(next) };
    }),
  activeSessionKey: null,
  setActiveSessionKey: (key) => set({ activeSessionKey: key }),
  draftOpen: false,
  setDraftOpen: (open) => set({ draftOpen: open }),
  showArchived: false,
  setShowArchived: (show) => set({ showArchived: show }),
  draftSettings: DEFAULT_DRAFT,
  replaceDraftSettings: (settings) => set({ draftSettings: settings }),
  patchDraftSettings: (updates) =>
    set((state) => ({
      draftSettings: {
        ...state.draftSettings,
        ...updates,
      },
    })),

  messages: {},
  setMessages: (sessionKey, messages) =>
    set((state) => ({
      messages: { ...state.messages, [sessionKey]: messages },
    })),
  addMessage: (sessionKey, message) =>
    set((state) => {
      const current = state.messages[sessionKey] || [];
      const existingIdx = current.findIndex((item) => item.localId === message.localId);
      if (existingIdx >= 0) {
        const next = [...current];
        next[existingIdx] = message;
        return { messages: { ...state.messages, [sessionKey]: next } };
      }
      return { messages: { ...state.messages, [sessionKey]: [...current, message] } };
    }),
  updateMessage: (sessionKey, localId, updates) =>
    set((state) => {
      const current = state.messages[sessionKey] || [];
      const existingIdx = current.findIndex((item) => item.localId === localId);
      if (existingIdx < 0) return state;
      const next = [...current];
      next[existingIdx] = { ...next[existingIdx], ...updates };
      return { messages: { ...state.messages, [sessionKey]: next } };
    }),
  pendingAssistants: {},
  registerPendingAssistant: (runId, sessionKey, localId) =>
    set((state) => ({
      pendingAssistants: {
        ...state.pendingAssistants,
        [runId]: { sessionKey, localId },
      },
    })),
  clearPendingAssistant: (runId) =>
    set((state) => {
      const next = { ...state.pendingAssistants };
      delete next[runId];
      return { pendingAssistants: next };
    }),

  pendingApproval: null,
  runPausedReason: null,
  approvalHistory: [],
  setPendingApproval: (req) =>
    set((state) => ({
      pendingApproval: req,
      runPausedReason: req ? 'awaiting_approval' : null,
      approvalHistory: req
        ? upsertInHistory(state.approvalHistory, req)
        : state.approvalHistory,
    })),
  resolveApproval: (approvalId, outcome) =>
    set((state) => {
      if (!state.pendingApproval || state.pendingApproval.approvalId !== approvalId) return state;
      const resolved: ApprovalRequest = {
        ...state.pendingApproval,
        status: outcome.decision === 'modified' ? 'modified' : outcome.decision === 'approved' ? 'approved' : 'rejected',
        outcome,
        resolvedAt: outcome.decidedAt,
      };
      return {
        pendingApproval: resolved,
        runPausedReason: null,
        approvalHistory: upsertInHistory(state.approvalHistory, resolved),
      };
    }),
  setRunPausedReason: (reason) => set({ runPausedReason: reason }),
  upsertApprovalInHistory: (req) =>
    set((state) => ({ approvalHistory: upsertInHistory(state.approvalHistory, req) })),
  loadApprovalHistory: (history) => set({ approvalHistory: history }),

  destinations: [],
  setDestinations: (destinations) => set({ destinations }),

  messagingConfig: null,
  setMessagingConfig: (config) => set({ messagingConfig: config }),

  runTimeline: null,
  setRunTimeline: (timeline) => set({ runTimeline: timeline }),

  composerOpen: false,
  composerTarget: null,
  composerMessage: '',
  setComposerOpen: (open) => set({ composerOpen: open }),
  setComposerTarget: (target) => set({ composerTarget: target }),
  setComposerMessage: (message) => set({ composerMessage: message }),
  resetComposer: () => set({ composerOpen: false, composerTarget: null, composerMessage: '' }),

  liveToolCalls: [],
  pushLiveToolCall: (call) =>
    set((state) => {
      // Dedupe: if a call with the same id already exists, replace it
      const next = state.liveToolCalls.filter((c) => c.id !== call.id);
      return { liveToolCalls: [...next, call] };
    }),
  clearLiveToolCalls: () => set({ liveToolCalls: [] }),

  lastTurnState: null,
  setLastTurnState: (snapshot) => set({ lastTurnState: snapshot }),

  providerAuthStatuses: {},
  setProviderAuthStatus: (providerId, status) =>
    set((state) => ({
      providerAuthStatuses: { ...state.providerAuthStatuses, [providerId]: status },
    })),
  clearProviderAuthStatus: (providerId) =>
    set((state) => {
      const next = { ...state.providerAuthStatuses };
      delete next[providerId];
      return { providerAuthStatuses: next };
    }),

  patProfile: null,
  setPatProfile: (profile) => set({ patProfile: profile }),

  returnBriefing: null,
  setReturnBriefing: (briefing) => set({ returnBriefing: briefing }),
  dismissReturnBriefing: () => set({ returnBriefing: null }),

  profileChangelog: [],
  setProfileChangelog: (changelog) => set({ profileChangelog: changelog }),
  prependProfileChangelogItem: (item) =>
    set((state) => ({ profileChangelog: [item, ...state.profileChangelog] })),
}));
