/**
 * controllers/sessions.js — session and catalog load/select/create/rename/archive flows.
 */

import {
  state,
  draftState,
  sessionCatalog,
  providerCatalog,
  modelCatalog,
  profileCatalog,
  taskModeCatalog,
  activeSession,
  preferredProviderId,
  DEFAULT_CHAT_PROVIDER_ID,
  DEFAULT_PROFILE_ID,
  DEFAULT_TASK_MODE_ID,
} from '../state.js';
import {
  draftModelSelectEl,
  draftProfileSelectEl,
  draftProviderSelectEl,
  draftTaskSelectEl,
  emptyState,
  messagesEl,
} from '../dom.js';
import { sendReq } from '../rpc.js';
import { addMessage, describeError, logClientError, showError } from '../render/messages.js';
import { setHeaderChrome, syncProviderSelect, syncModelSelect, syncProfileSelect, syncTaskModeSelect } from '../render/header.js';
import { renderSessions } from '../render/sessions.js';

export async function loadProviders() {
  const res = await sendReq('providers.list', {});
  Object.keys(providerCatalog).forEach((key) => delete providerCatalog[key]);
  (res.providers || []).forEach((provider) => {
    providerCatalog[provider.id] = {
      displayName: provider.displayName || provider.id,
      available: provider.available !== false,
      error: provider.error || '',
      capabilities: provider.capabilities || {},
      defaultModel: provider.defaultModel || '',
    };
  });
  if (!providerCatalog[draftState.provider] || providerCatalog[draftState.provider].available === false) {
    draftState.provider = preferredProviderId();
  }
  syncProviderSelect();
}

export async function loadModels(providerId) {
  if (!providerId) return;
  try {
    const res = await sendReq('models.list', { provider: providerId, kind: 'chat' });
    modelCatalog[providerId] = (res.models || []).filter((model) => model.provider === providerId);
  } catch (err) {
    logClientError(`models.list failed for ${providerId}`, err);
    modelCatalog[providerId] = [];
  }

  if (!activeSession()) {
    const list = modelCatalog[providerId] || [];
    if (!draftState.model || !list.some((item) => item.id === draftState.model)) {
      const provider = providerCatalog[providerId];
      draftState.model = provider && provider.defaultModel ? provider.defaultModel : ((list[0] && list[0].id) || '');
    }
  }

  syncModelSelect();
  setHeaderChrome();
}

export async function loadPrompts() {
  const res = await sendReq('prompts.list', {});
  Object.keys(profileCatalog).forEach((key) => delete profileCatalog[key]);
  Object.keys(taskModeCatalog).forEach((key) => delete taskModeCatalog[key]);
  (res.profiles || []).forEach((prompt) => {
    profileCatalog[prompt.id] = { id: prompt.id, name: prompt.name || prompt.id };
  });
  (res.taskModes || []).forEach((prompt) => {
    taskModeCatalog[prompt.id] = { id: prompt.id, name: prompt.name || prompt.id };
  });
  if (!profileCatalog[draftState.systemPromptId]) {
    draftState.systemPromptId = profileCatalog[DEFAULT_PROFILE_ID] ? DEFAULT_PROFILE_ID : (Object.keys(profileCatalog)[0] || '');
  }
  if (!taskModeCatalog[draftState.taskPromptId]) {
    draftState.taskPromptId = taskModeCatalog[DEFAULT_TASK_MODE_ID] ? DEFAULT_TASK_MODE_ID : (Object.keys(taskModeCatalog)[0] || '');
  }
  syncProfileSelect();
  syncTaskModeSelect();
}

export async function loadSessions() {
  const res = await sendReq('sessions.list', {});
  Object.keys(sessionCatalog).forEach((key) => delete sessionCatalog[key]);
  (res.sessions || []).forEach((session) => {
    sessionCatalog[session.key || session.sessionId] = session;
  });
  renderSessions();
}

export async function loadHistory() {
  if (!state.currentSessionKey) {
    messagesEl.innerHTML = '';
    if (emptyState) {
      messagesEl.appendChild(emptyState);
      emptyState.style.display = 'block';
    }
    return;
  }

  try {
    const res = await sendReq('chat.history', { sessionKey: state.currentSessionKey, limit: 100 });
    const list = res.messages || [];
    messagesEl.innerHTML = '';
    if (emptyState) {
      messagesEl.appendChild(emptyState);
      emptyState.style.display = list.length ? 'none' : 'block';
    }
    list.forEach((message) => {
      const role = (message.role || 'user').toLowerCase();
      const content = typeof message.content === 'string' ? message.content : (message.content && message.content.text) || '';
      addMessage(role, content, false, role === 'assistant' ? { provider: message.provider, model: message.model, toolExecution: message.toolExecution } : null);
    });
    messagesEl.scrollTop = messagesEl.scrollHeight;
  } catch (err) {
    logClientError('chat.history failed', err);
    showError(describeError(err, 'Unable to load chat history.'));
    if (emptyState) emptyState.style.display = 'block';
  }
}

export async function selectSession(key) {
  state.currentSessionKey = key;
  const session = activeSession();
  if (session) {
    draftState.provider = session.provider || preferredProviderId();
    draftState.model = session.model || '';
    draftState.systemPromptId = session.systemPromptId || draftState.systemPromptId || DEFAULT_PROFILE_ID;
    draftState.taskPromptId = session.taskPromptId || draftState.taskPromptId || DEFAULT_TASK_MODE_ID;
    await loadModels(draftState.provider);
    syncProfileSelect();
    syncTaskModeSelect();
  }
  renderSessions();
  setHeaderChrome();
  await loadHistory();
}

export async function beginDraft(preferred) {
  state.currentSessionKey = null;
  draftState.provider = preferred && preferred.provider ? preferred.provider : preferredProviderId();
  draftState.model = preferred && preferred.model ? preferred.model : '';
  draftState.systemPromptId = preferred && preferred.systemPromptId ? preferred.systemPromptId : (draftState.systemPromptId || DEFAULT_PROFILE_ID);
  draftState.taskPromptId = preferred && preferred.taskPromptId ? preferred.taskPromptId : (draftState.taskPromptId || DEFAULT_TASK_MODE_ID);
  syncProviderSelect();
  syncProfileSelect();
  syncTaskModeSelect();
  await loadModels(draftState.provider);
  renderSessions();
  setHeaderChrome();
  await loadHistory();
}

export async function createSessionFromDraft() {
  const provider = draftProviderSelectEl.value || draftState.provider || preferredProviderId();
  const model = draftModelSelectEl.dataset.noModels === '1' ? null : (draftModelSelectEl.value || null);
  const systemPromptId = draftProfileSelectEl.value || draftState.systemPromptId || undefined;
  const taskPromptId = draftTaskSelectEl.value || draftState.taskPromptId || undefined;

  if (!provider) {
    throw new Error('Choose a runtime first.');
  }

  const res = await sendReq('sessions.create', { provider, model, systemPromptId, taskPromptId });
  const session = res.session;
  if (!session || !session.key) {
    throw new Error('Session creation failed.');
  }
  sessionCatalog[session.key] = session;
  draftState.provider = provider;
  draftState.model = model || '';
  draftState.systemPromptId = systemPromptId || DEFAULT_PROFILE_ID;
  draftState.taskPromptId = taskPromptId || DEFAULT_TASK_MODE_ID;
  await selectSession(session.key);
  return session;
}

export async function renameCurrentSession() {
  const session = activeSession();
  if (!session) return;
  const proposed = window.prompt('Session title', session.title || session.key || '');
  if (proposed == null) return;
  const title = proposed.trim();
  const res = await sendReq('sessions.rename', { key: session.key, title: title || undefined });
  if (res.session) {
    sessionCatalog[res.session.key] = res.session;
    await selectSession(res.session.key);
  }
}

export async function archiveCurrentSession() {
  const session = activeSession();
  if (!session) return;
  await sendReq('sessions.archive', { key: session.key, archived: true });
  delete sessionCatalog[session.key];
  const nextKey = Object.keys(sessionCatalog)[0] || null;
  renderSessions();
  if (nextKey) {
    await selectSession(nextKey);
  } else {
    await beginDraft({
      provider: session.provider,
      model: session.model,
      systemPromptId: session.systemPromptId,
      taskPromptId: session.taskPromptId,
    });
  }
}

export function scheduleSessionRefresh() {
  if (!state.currentSessionKey) return;
  const key = state.currentSessionKey;
  [1200, 2600, 4200].forEach((delayMs) => {
    setTimeout(async () => {
      if (state.currentSessionKey !== key) return;
      try {
        await loadSessions();
        if (sessionCatalog[key]) await selectSession(key);
      } catch (err) {
        logClientError('session refresh failed', err);
      }
    }, delayMs);
  });
}
