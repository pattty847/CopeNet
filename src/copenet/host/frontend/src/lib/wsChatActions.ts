import { useAppStore } from '../store/useAppStore';
import type { ChatAttachment, Message, Session } from '../types/backend';
import type { MarketContext } from '../sections/market/chartAgent/types';
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

export interface SendMessageToSessionOptions {
  session: Session;
  message: string;
  attachments?: ChatAttachment[];
  requestedToolIds?: string[];
  marketContext?: MarketContext;
  displayContext?: { symbol: string; timeframe: 'D' | 'W' | 'M' };
  idempotencyKey?: string;
  runtimeOverride?: { model?: string; taskPromptId?: string };
}

/** Send to a captured session; this never selects or creates an Agents draft. */
export async function sendMessageToSessionAction(
  request: WsRpcRequest,
  options: SendMessageToSessionOptions,
): Promise<{ runId?: string; status?: string } | undefined> {
  const { session, message, attachments, requestedToolIds } = options;
  const trimmed = message.trim();
  const readyAttachments = (attachments || []).filter((item) => item.attachmentId);
  const requestedTools = [...new Set((requestedToolIds || []).map((toolId) => toolId.trim()).filter(Boolean))];
  if (!trimmed && readyAttachments.length === 0) return;
  const store = useAppStore.getState();
  store.clearAppError();
  try {
    // Mid-session runtime mutability (A + B1): a locked session may carry a pending
    // model / Access override. Apply it on this send; the backend reconciles the
    // binding, then refreshSessions pulls the canonical values and we clear it.
    const override = options.runtimeOverride;
    const effectiveModel = override?.model || session.model;
    const effectiveTaskPromptId = override?.taskPromptId ?? session.taskPromptId;

    const userMessage: Message = {
      localId: options.idempotencyKey ? `user:${session.key}:${options.idempotencyKey}` : makeLocalId('user'),
      sessionKey: session.key,
      runId: options.idempotencyKey || null,
      role: 'user',
      content: trimmed,
      attachments: readyAttachments.length > 0 ? readyAttachments : null,
      requestedToolIds: requestedTools.length > 0 ? requestedTools : null,
      marketContext: options.marketContext ? { ...options.marketContext, ...options.displayContext } : null,
      timestamp: new Date().toISOString(),
      provider: session.provider,
      model: effectiveModel,
      providerSessionId: session.providerSessionId,
      state: 'final',
      toolExecution: null,
      errorMessage: null,
      optimistic: true,
    };
    if (!options.idempotencyKey || !(store.messages[session.key] || []).some((item) => item.runId === options.idempotencyKey && item.role === 'user')) {
      store.addMessage(session.key, userMessage);
    }

    const ensureAssistant = (runId: string) => {
      const current = useAppStore.getState();
      const existing = (current.messages[session.key] || []).find((item) => item.runId === runId && item.role === 'assistant');
      if (existing && (current.pendingAssistants[runId] || existing.state === 'final')) return;
      store.clearLiveToolCalls(runId);
      store.setLastTurnState(session.key, null);
      const assistantMessage: Message = {
        localId: options.idempotencyKey ? `assistant:${session.key}:${runId}` : makeLocalId('assistant'),
        sessionKey: session.key,
        runId,
        role: 'assistant',
        content: '',
        marketContext: options.marketContext ? { ...options.marketContext, ...options.displayContext } : null,
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

    };
    // A fast provider can emit tools and final before the response promise is
    // resumed. The caller's stable run ID lets us register its target first.
    if (options.marketContext && options.idempotencyKey) ensureAssistant(options.idempotencyKey);

    const payload = await request<{ runId?: string; status?: string }>('chat.send', {
      sessionKey: session.key,
      message: trimmed,
      attachmentIds: readyAttachments.map((item) => item.attachmentId),
      requestedToolIds: requestedTools,
      provider: session.provider,
      model: effectiveModel || undefined,
      systemPromptId: session.systemPromptId || undefined,
      taskPromptId: effectiveTaskPromptId || undefined,
      personaId: session.personaId || undefined,
      personaFlavorId: session.personaFlavorId || undefined,
      personaPrivacyTier: session.personaPrivacyTier || undefined,
      idempotencyKey: options.idempotencyKey,
      marketContext: options.marketContext,
    });
    store.clearSessionRuntimeOverride(session.key);
    const runId = payload.runId ? String(payload.runId) : null;
    const status = payload.status ? String(payload.status) : '';

    if (status === 'interrupted' || status === 'failed') {
      throw new Error('This chart request was interrupted. Inspect its history before starting a new request.');
    }

    if (status === 'in_flight' && !options.marketContext) {
      throw new Error('This session already has a reply in progress.');
    }

    if (runId && status !== 'cached' && status !== 'completed') {
      ensureAssistant(runId);
      if (useAppStore.getState().pendingAssistants[runId]) store.setActiveRun(session.key, runId);
    } else if (runId) {
      store.clearPendingAssistant(runId);
      store.clearActiveRun(session.key, runId);
    }
    return payload;
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unable to send message.';
    const targetSessionKey = session.key;
    if (options.idempotencyKey) {
      const target = useAppStore.getState().pendingAssistants[options.idempotencyKey];
      if (target) store.updateMessage(session.key, target.localId, { state: 'error', errorMessage, optimistic: false });
      store.clearPendingAssistant(options.idempotencyKey);
      store.clearActiveRun(session.key, options.idempotencyKey);
    }
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

/** Agents' existing draft controller delegates once it has a concrete session. */
export async function sendMessageAction(
  request: WsRpcRequest,
  message: string,
  attachments?: ChatAttachment[],
  requestedToolIds?: string[],
): Promise<void> {
  if (!message.trim() && !(attachments || []).some((item) => item.attachmentId)) return;
  const store = useAppStore.getState();
  const originSessionKey = store.activeSessionKey || DRAFT_TRANSCRIPT_SESSION_KEY;
  let createdSession: Session;
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

    createdSession = session;
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unable to create session.';
    store.setAppError(errorMessage);
    store.addMessage(originSessionKey, {
      localId: makeLocalId('system'), sessionKey: originSessionKey, runId: null,
      role: 'system', content: errorMessage, timestamp: new Date().toISOString(),
      provider: null, model: null, providerSessionId: null, state: 'error',
      toolExecution: null, errorMessage, optimistic: false,
    });
    throw error;
  }
  await sendMessageToSessionAction(request, {
    session: createdSession, message, attachments, requestedToolIds,
    runtimeOverride: store.sessionRuntimeOverrides[createdSession.key],
  });
}
