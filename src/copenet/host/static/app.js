/**
 * app.js — bootstrap entry point.
 *
 * Imports all modules, wires DOM event listeners, and kicks off the WebSocket
 * connection. All logic lives in js/controllers/ and js/render/.
 */

import {
  draftState,
  draftProviderSelectEl,
  draftModelSelectEl,
  draftProfileSelectEl,
  draftTaskSelectEl,
  sendBtn,
  newChatBtn,
  promptSettingsBtn,
  renameSessionBtn,
  archiveSessionBtn,
  inputEl,
  sessionsList,
  preferredProviderId,
  providerForUi,
  modelForUi,
  profileForUi,
  taskModeForUi,
  DEFAULT_CHAT_PROVIDER_ID,
  DEFAULT_PROFILE_ID,
  DEFAULT_TASK_MODE_ID,
} from './js/state.js';

import { setHeaderChrome } from './js/render/header.js';
import { showError, hideError } from './js/render/messages.js';
import { loadModels } from './js/controllers/sessions.js';
import {
  selectSession,
  beginDraft,
  renameCurrentSession,
  archiveCurrentSession,
} from './js/controllers/sessions.js';
import { sendMessage, connect } from './js/controllers/chat.js';

// ---------------------------------------------------------------------------
// Draft config change handlers
// ---------------------------------------------------------------------------

draftProviderSelectEl.addEventListener('change', async () => {
  draftState.provider = draftProviderSelectEl.value || preferredProviderId();
  draftState.model = '';
  await loadModels(draftState.provider);
  setHeaderChrome();
});

draftModelSelectEl.addEventListener('change', () => {
  draftState.model = draftModelSelectEl.value || '';
  setHeaderChrome();
});

draftProfileSelectEl.addEventListener('change', () => {
  draftState.systemPromptId = draftProfileSelectEl.value || DEFAULT_PROFILE_ID;
  setHeaderChrome();
});

draftTaskSelectEl.addEventListener('change', () => {
  draftState.taskPromptId = draftTaskSelectEl.value || DEFAULT_TASK_MODE_ID;
  setHeaderChrome();
});

// ---------------------------------------------------------------------------
// Session list click delegation
// ---------------------------------------------------------------------------

sessionsList.addEventListener('click', (e) => {
  const item = e.target.closest('[data-session-key]');
  if (item) selectSession(item.dataset.sessionKey);
});

// ---------------------------------------------------------------------------
// Toolbar buttons
// ---------------------------------------------------------------------------

sendBtn.addEventListener('click', sendMessage);

newChatBtn.addEventListener('click', () => {
  hideError();
  beginDraft({
    provider: providerForUi(),
    model: modelForUi(),
    systemPromptId: profileForUi(),
    taskPromptId: taskModeForUi(),
  });
});

promptSettingsBtn.addEventListener('click', () => {
  showError('Advanced prompt settings are coming soon. For now, use Profile and Task Mode in the draft header.');
});

renameSessionBtn.addEventListener('click', renameCurrentSession);
archiveSessionBtn.addEventListener('click', archiveCurrentSession);

inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ---------------------------------------------------------------------------
// Boot
// ---------------------------------------------------------------------------

connect();
