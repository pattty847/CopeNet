import { create } from 'zustand';
import { DraftSettings, Message, Model, PromptOption, Provider, Session, ToolDescriptor, WsStatus } from '../types/backend';

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

  providers: Provider[];
  modelsByProvider: Record<string, Model[]>;
  loadedModelProviders: Record<string, boolean>;
  tools: ToolDescriptor[];
  profiles: PromptOption[];
  taskModes: PromptOption[];
  setProviders: (providers: Provider[]) => void;
  setModelsForProvider: (providerId: string, models: Model[]) => void;
  setTools: (tools: ToolDescriptor[]) => void;
  setPromptCatalog: (profiles: PromptOption[], taskModes: PromptOption[]) => void;

  sessions: Session[];
  setSessions: (sessions: Session[]) => void;
  upsertSession: (session: Session) => void;
  activeSessionKey: string | null;
  setActiveSessionKey: (key: string | null) => void;
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
  model: '',
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

  providers: [],
  modelsByProvider: {},
  loadedModelProviders: {},
  tools: [],
  profiles: [],
  taskModes: [],
  setProviders: (providers) => set({ providers }),
  setModelsForProvider: (providerId, models) =>
    set((state) => ({
      modelsByProvider: { ...state.modelsByProvider, [providerId]: models },
      loadedModelProviders: { ...state.loadedModelProviders, [providerId]: true },
    })),
  setTools: (tools) => set({ tools }),
  setPromptCatalog: (profiles, taskModes) => set({ profiles, taskModes }),

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
