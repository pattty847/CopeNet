import { useAppStore } from '../store/useAppStore';
import type {
  ApprovalRequest,
  MemoryItem,
  ProfileChangelogItem,
  PulseRecord,
  Session,
} from '../types/backend';
import {
  normalizeApprovalRequest,
  normalizeIdentityContext,
  normalizeMemoryItem,
  normalizeMessagingConfig,
  normalizePatProfile,
  normalizePersonaHome,
  normalizePersonaSettings,
  normalizeProfileChangelogItem,
  normalizePrompt,
  normalizeProvider,
  normalizePulse,
  normalizeReturnBriefing,
  normalizeRuntimeContext,
  normalizeSession,
  normalizeTool,
} from './wsNormalizers';
import { ensureDraftDefaultsAction } from './wsSessionActions';

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
      profilePayload,
      personaPayload,
      personaSettingsPayload,
      identityPayload,
      memoryPayload,
      changelogPayload,
      briefingPayload,
      runtimeContextPayload,
      pulsePayload,
      messagingPayload,
      approvalsPayload,
    ] = await Promise.all([
      request<{ providers: unknown[] }>('providers.list', {}),
      request<{ tools: unknown[] }>('tools.list', {}),
      request<{ profiles?: unknown[]; taskModes?: unknown[] }>('prompts.list', {}),
      request<{ sessions: unknown[] }>('sessions.list', { includeArchived: useAppStore.getState().showArchived }),
      request<{ profile?: unknown | null }>('profile.get', {}),
      request<{ persona?: unknown | null }>('persona.get', {}),
      request<{ settings?: unknown | null }>('persona.settings.get', {}),
      request<{ identityContext?: unknown | null }>('identity.context', {}),
      request<{ items?: unknown[] }>('memory.list', { limit: 24 }),
      request<{ changelog?: unknown[] }>('profile.changelog', { limit: 20 }),
      request<{ briefing?: unknown | null }>('briefing.get', {}),
      request<{ runtimeContext?: unknown | null }>('runtime.context', {}),
      request<{ pulses?: unknown[] }>('pulse.list', {}),
      request<{ config?: unknown | null }>('messaging.config.get', {}),
      request<{ approvals?: unknown[] }>('approvals.list', {}),
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
    void refreshMemoryDrafts();
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
      await loadHistory(nextKey);
    }
    // Phase 4.6: reconcile any runs that were in-flight when the socket dropped.
    await reconcilePendingRuns(sessions);
  } catch (error) {
    useAppStore.getState().setAppError(error instanceof Error ? error.message : 'Bootstrap failed.');
  }
}
