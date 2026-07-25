import type { StoreApi } from 'zustand';
import type {
  ApprovalOutcome,
  ApprovalRequest,
  LiveToolCall,
  Session,
  TurnStateSnapshot,
} from '../types/backend';

export interface SessionRuntimeSlice {
  activeRunsBySession: Record<string, string>;
  liveToolCallsByRun: Record<string, LiveToolCall[]>;
  lastTurnStateBySession: Record<string, TurnStateSnapshot>;
  pendingApprovalsById: Record<string, ApprovalRequest>;
  approvalHistory: ApprovalRequest[];
  syncActiveRuns: (sessions: Session[]) => void;
  setActiveRun: (sessionKey: string, runId: string | null) => void;
  clearActiveRun: (sessionKey: string, runId?: string) => void;
  pushLiveToolCall: (runId: string, call: LiveToolCall) => void;
  clearLiveToolCalls: (runId: string) => void;
  setLastTurnState: (sessionKey: string, snapshot: TurnStateSnapshot | null) => void;
  setPendingApprovals: (requests: ApprovalRequest[]) => void;
  setPendingApproval: (request: ApprovalRequest | null) => void;
  resolveApproval: (approvalId: string, outcome: ApprovalOutcome) => void;
  upsertApprovalInHistory: (request: ApprovalRequest) => void;
  loadApprovalHistory: (history: ApprovalRequest[]) => void;
}

function upsertApproval(history: ApprovalRequest[], request: ApprovalRequest): ApprovalRequest[] {
  return [request, ...history.filter((item) => item.approvalId !== request.approvalId)];
}

export function createSessionRuntimeSlice<T extends SessionRuntimeSlice>(
  set: StoreApi<T>['setState'],
): SessionRuntimeSlice {
  return {
    activeRunsBySession: {},
    liveToolCallsByRun: {},
    lastTurnStateBySession: {},
    pendingApprovalsById: {},
    approvalHistory: [],
    syncActiveRuns: (sessions) =>
      set({
        activeRunsBySession: Object.fromEntries(
          sessions
            .filter((session) => Boolean(session.inFlightRunId))
            .map((session) => [session.key, session.inFlightRunId as string]),
        ),
      } as Partial<T>),
    setActiveRun: (sessionKey, runId) =>
      set((state) => {
        const activeRunsBySession = { ...state.activeRunsBySession };
        if (runId) activeRunsBySession[sessionKey] = runId;
        else delete activeRunsBySession[sessionKey];
        return { activeRunsBySession } as Partial<T>;
      }),
    clearActiveRun: (sessionKey, runId) =>
      set((state) => {
        if (runId && state.activeRunsBySession[sessionKey] !== runId) return {} as Partial<T>;
        const activeRunsBySession = { ...state.activeRunsBySession };
        delete activeRunsBySession[sessionKey];
        return { activeRunsBySession } as Partial<T>;
      }),
    pushLiveToolCall: (runId, call) =>
      set((state) => {
        const current = state.liveToolCallsByRun[runId] || [];
        const next = [...current.filter((item) => item.id !== call.id), call];
        return {
          liveToolCallsByRun: { ...state.liveToolCallsByRun, [runId]: next },
        } as Partial<T>;
      }),
    clearLiveToolCalls: (runId) =>
      set((state) => ({
        liveToolCallsByRun: { ...state.liveToolCallsByRun, [runId]: [] },
      } as Partial<T>)),
    setLastTurnState: (sessionKey, snapshot) =>
      set((state) => {
        const lastTurnStateBySession = { ...state.lastTurnStateBySession };
        if (snapshot) lastTurnStateBySession[sessionKey] = snapshot;
        else delete lastTurnStateBySession[sessionKey];
        return { lastTurnStateBySession } as Partial<T>;
      }),
    setPendingApprovals: (requests) =>
      set((state) => ({
        pendingApprovalsById: Object.fromEntries(requests.map((request) => [request.approvalId, request])),
        approvalHistory: requests.reduce(upsertApproval, state.approvalHistory),
      } as Partial<T>)),
    setPendingApproval: (request) =>
      set((state) => {
        if (!request) return {} as Partial<T>;
        return {
          pendingApprovalsById: { ...state.pendingApprovalsById, [request.approvalId]: request },
          approvalHistory: upsertApproval(state.approvalHistory, request),
        } as Partial<T>;
      }),
    resolveApproval: (approvalId, outcome) =>
      set((state) => {
        const current = state.pendingApprovalsById[approvalId]
          || state.approvalHistory.find((item) => item.approvalId === approvalId);
        if (!current) return {} as Partial<T>;
        const resolved: ApprovalRequest = {
          ...current,
          status: outcome.decision === 'modified'
            ? 'modified'
            : outcome.decision === 'approved' ? 'approved' : 'rejected',
          outcome,
          resolvedAt: outcome.decidedAt,
        };
        const pendingApprovalsById = { ...state.pendingApprovalsById };
        delete pendingApprovalsById[approvalId];
        return {
          pendingApprovalsById,
          approvalHistory: upsertApproval(state.approvalHistory, resolved),
        } as Partial<T>;
      }),
    upsertApprovalInHistory: (request) =>
      set((state) => ({ approvalHistory: upsertApproval(state.approvalHistory, request) } as Partial<T>)),
    loadApprovalHistory: (history) => set({ approvalHistory: history } as Partial<T>),
  };
}
