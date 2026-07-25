import { useAppStore } from '../store/useAppStore';
import type { ChatAttachment, Message } from '../types/backend';
import { DRAFT_TRANSCRIPT_SESSION_KEY } from './personaCommands';
import { makeLocalId, normalizeSession } from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function decideApprovalAction(
  request: WsRpcRequest,
  approvalId: string,
  decision: 'approved' | 'approved_always' | 'rejected',
  note?: string,
): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>('chat.decideApproval', { approvalId, decision, note });
}

export async function abortActiveRunAction(
  request: WsRpcRequest,
  sessionKey: string,
  runId: string,
): Promise<void> {
  await request('chat.abort', {
    sessionKey,
    runId,
  });
}

export async function sendMessageAction(
  request: WsRpcRequest,
  message: string,
  attachments?: ChatAttachment[],
): Promise<void> {
  const trimmed = message.trim();
  const readyAttachments = (attachments || []).filter((item) => item.attachmentId);
  // An image-only send (no text) is valid as long as something is attached.
  if (!trimmed && readyAttachments.length === 0) return;

  const store = useAppStore.getState();
  store.clearAppError();

  try {
    let session = store.sessions.find((item) => item.key === store.activeSessionKey) || null;
    if (!session) {
      const draft = store.draftSettings;
      const createPayload = await request<{ session: unknown }>('sessions.create', {
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
      attachments: readyAttachments.length > 0 ? readyAttachments : null,
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

    const payload = await request<{ runId?: string; status?: string }>('chat.send', {
      sessionKey: session.key,
      message: trimmed,
      attachmentIds: readyAttachments.map((item) => item.attachmentId),
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
      store.clearLiveToolCalls(runId);
      store.setLastTurnState(session.key, null);

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
      store.setActiveRun(session.key, runId);
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
