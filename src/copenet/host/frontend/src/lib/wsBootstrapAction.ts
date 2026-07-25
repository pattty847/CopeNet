import { useAppStore } from '../store/useAppStore';
import type {
  ApprovalRequest,
  MemoryItem,
  PulseRecord,
  Session,
} from '../types/backend';
import {
  normalizeApprovalRequest,
  normalizeMemoryItem,
  normalizeMessagingConfig,
  normalizePersonaHome,
  normalizePersonaSettings,
  normalizePrompt,
  normalizeProvider,
  normalizePulse,
  normalizeReturnBriefing,
  normalizeRuntimeContext,
  normalizeSession,
  normalizeTool,
} from './wsNormalizers';
import { ensureDraftDefaultsAction } from './wsSessionActions';
import { normalizeFleetRoom } from './wsFleetRpc';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function bootstrapAction(
  request: WsRpcRequest,
  loadHistory: (sessionKey: string) => Promise<void>,
  reconcilePendingRuns: (sessions: Session[]) => Promise<void>,
  refreshMemoryDrafts: () => Promise<void>,
): Promise<void> {
  try {
    const [
      providersPayload,
      toolsPayload,
      promptsPayload,
      sessionsPayload,
      personaPayload,
      personaSettingsPayload,
      memoryPayload,
      briefingPayload,
      runtimeContextPayload,
      pulsePayload,
      messagingPayload,
      approvalsPayload,
      fleetPayload,
    ] = await Promise.all([
      request<{ providers: unknown[] }>('providers.list', {}),
      request<{ tools: unknown[] }>('tools.list', {}),
      request<{ profiles?: unknown[]; taskModes?: unknown[] }>('prompts.list', {}),
      request<{ sessions: unknown[] }>('sessions.list', { includeArchived: useAppStore.getState().showArchived }),
      request<{ persona?: unknown | null }>('persona.get', {}),
      request<{ settings?: unknown | null }>('persona.settings.get', {}),
      request<{ items?: unknown[] }>('memory.list', { limit: 24 }),
      request<{ briefing?: unknown | null }>('briefing.get', {}),
      request<{ runtimeContext?: unknown | null }>('runtime.context', {}),
      request<{ pulses?: unknown[] }>('pulse.list', {}),
      request<{ config?: unknown | null }>('messaging.config.get', {}),
      request<{ approvals?: unknown[] }>('approvals.list', {}),
      // Fleet is additive: an older backend without fleet.* must not take down
      // the whole bootstrap (pulse, sessions, briefing) with one rejection.
      request<{ rooms?: unknown[] }>('fleet.list', {}).catch(() => ({ rooms: [] as unknown[] })),
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
    store.syncActiveRuns(sessions);
    store.setPersonaHome(normalizePersonaHome(personaPayload.persona));
    store.setPersonaSettings(normalizePersonaSettings(personaSettingsPayload.settings));
    store.setMemoryItems(
      Array.isArray(memoryPayload.items)
        ? memoryPayload.items.map(normalizeMemoryItem).filter((item): item is MemoryItem => item != null)
        : [],
    );
    void refreshMemoryDrafts();
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
    store.setPendingApprovals(pendingApprovals);
    store.setFleetRooms(Array.isArray(fleetPayload.rooms) ? fleetPayload.rooms.map(normalizeFleetRoom) : []);
    ensureDraftDefaultsAction();

    const currentKey = store.activeSessionKey;
    const hasCurrent = currentKey && sessions.some((session) => session.key === currentKey);
    const nextKey = hasCurrent ? currentKey : store.draftOpen ? null : sessions[0]?.key || null;
    store.setActiveSessionKey(nextKey);
    if (nextKey) {
      store.setDraftOpen(false);
      await loadHistory(nextKey);
    }
    // Phase 4.6: reconcile any runs that were in-flight when the socket dropped.
    await reconcilePendingRuns(sessions);
  } catch (error) {
    useAppStore.getState().setAppError(error instanceof Error ? error.message : 'Bootstrap failed.');
  }
}
