import { create } from 'zustand';
import { DataToolsRoute, DraftSettings, MediaAsset, Message, Model, PromptOption, Provider, Session, ToolDescriptor, WsStatus } from '../types/backend';
import type { InspectorTarget } from '../runtime/types';

export type AppSection = 'home' | 'agents' | 'workflows' | 'data-tools' | 'observability' | 'experiments';
export type ThemeMode = 'light' | 'dark';
export type RightPanelTab = 'runtime' | 'artifacts' | 'activity';
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

  primaryNavCollapsed: boolean;
  setPrimaryNavCollapsed: (collapsed: boolean) => void;
  sidebarOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
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
}

function sortSessions(sessions: Session[]) {
  return [...sessions].sort((a, b) => String(b.updatedAt || '').localeCompare(String(a.updatedAt || '')));
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

  primaryNavCollapsed: false,
  setPrimaryNavCollapsed: (collapsed) => set({ primaryNavCollapsed: collapsed }),
  sidebarOpen: true,
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
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
}));
