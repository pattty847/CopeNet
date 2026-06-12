/**
 * state.js — shared mutable state, catalog data, and selector helpers.
 *
 * All modules import from here. Mutations to object/array exports are visible
 * everywhere because JS objects are shared by reference.
 */

export const DEFAULT_CHAT_PROVIDER_ID = 'openai-codex';
export const DEFAULT_PROFILE_ID = 'default';
export const DEFAULT_TASK_MODE_ID = 'none';

/**
 * Primitive mutable state lives on this object so all modules share one reference.
 * Read: state.connected   Write: state.connected = true
 */
export const state = {
  /** @type {WebSocket|null} */
  ws: null,
  connected: false,
  /** @type {string|null} */
  currentSessionKey: null,
  /** @type {string|null} */
  activeRunId: null,
  /** @type {Element|null} */
  pendingIndicatorEl: null,
  bootstrapped: false,
};

export const chatSendAckTimers = {};
export const chatSendAckHandlers = {};

/** @type {Record<string, object>} */
export const sessionCatalog = {};

export const draftState = {
  provider: DEFAULT_CHAT_PROVIDER_ID,
  model: '',
  systemPromptId: DEFAULT_PROFILE_ID,
  taskPromptId: DEFAULT_TASK_MODE_ID,
};

/** @type {Record<string, { displayName: string, available: boolean, error: string, capabilities?: Record<string, boolean>, defaultModel?: string }>} */
export const providerCatalog = {};
/** @type {Record<string, Array<{id: string, displayName: string, provider: string, description?: string, kind?: string}>>} */
export const modelCatalog = {};
/** @type {Record<string, { id: string, name: string }>} */
export const profileCatalog = {};
export const taskModeCatalog = {};

// ---------------------------------------------------------------------------
// Derived state helpers
// ---------------------------------------------------------------------------

export function activeSession() {
  return state.currentSessionKey ? sessionCatalog[state.currentSessionKey] || null : null;
}

export function isDraftMode() {
  return !activeSession();
}

export function sessionDisplayTitle(session) {
  if (!session) return 'New Chat';
  return (session.title || '').trim() || session.key || 'Untitled Session';
}

export function labelForProviderId(id) {
  if (!id) return 'Assistant';
  const row = providerCatalog[id];
  if (row && row.displayName) return row.displayName;
  return String(id)
    .split(/[-_]/)
    .filter(Boolean)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

export function labelForModel(providerId, modelId) {
  if (!modelId) {
    return providerId === 'openai-codex' ? 'Managed by provider' : 'No model selected';
  }
  const list = modelCatalog[providerId] || [];
  const row = list.find((item) => item.id === modelId);
  return row ? row.displayName : modelId;
}

export function labelForProfile(promptId) {
  if (!promptId) return 'None';
  const row = profileCatalog[promptId];
  return row ? row.name : promptId;
}

export function labelForTaskMode(taskPromptId) {
  if (!taskPromptId || taskPromptId === DEFAULT_TASK_MODE_ID) return 'General';
  const row = taskModeCatalog[taskPromptId];
  return row ? row.name : taskPromptId;
}

export function providerForUi() {
  const session = activeSession();
  return (session && session.provider) || draftState.provider || DEFAULT_CHAT_PROVIDER_ID;
}

export function modelForUi() {
  const session = activeSession();
  return (session && session.model) || draftState.model || '';
}

export function profileForUi() {
  const session = activeSession();
  return (session && session.systemPromptId) || draftState.systemPromptId || DEFAULT_PROFILE_ID;
}

export function taskModeForUi() {
  const session = activeSession();
  return (session && session.taskPromptId) || draftState.taskPromptId || DEFAULT_TASK_MODE_ID;
}

export function preferredProviderId() {
  const ranked = ['lm-studio', 'ollama', 'openai-codex'];
  for (const id of ranked) {
    const row = providerCatalog[id];
    if (row && row.available !== false) return id;
  }
  return ranked.find((id) => providerCatalog[id]) || DEFAULT_CHAT_PROVIDER_ID;
}

export function formatTimestamp(iso) {
  if (!iso) return '';
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return '';
  const diffMs = Date.now() - dt.getTime();
  const diffMin = Math.round(diffMs / 60000);
  if (diffMin < 1) return 'just now';
  if (diffMin < 60) return diffMin + 'm ago';
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return diffHr + 'h ago';
  const diffDay = Math.round(diffHr / 24);
  if (diffDay < 7) return diffDay + 'd ago';
  return dt.toLocaleString();
}
