/**
 * render/header.js — header badges, draft config panel, and select sync.
 */

import {
  state,
  draftState,
  providerCatalog,
  modelCatalog,
  profileCatalog,
  taskModeCatalog,
  activeSession,
  isDraftMode,
  sessionDisplayTitle,
  labelForProviderId,
  labelForModel,
  labelForProfile,
  labelForTaskMode,
  providerForUi,
  modelForUi,
  profileForUi,
  taskModeForUi,
  preferredProviderId,
  DEFAULT_CHAT_PROVIDER_ID,
  DEFAULT_PROFILE_ID,
  DEFAULT_TASK_MODE_ID,
} from '../state.js';
import {
  archiveSessionBtn,
  chatLockBadgeEl,
  chatModeBadgeEl,
  chatModelBadgeEl,
  chatProfileBadgeEl,
  chatProviderBadgeEl,
  chatSubtitleEl,
  chatTitleEl,
  composerBannerEl,
  draftConfigEl,
  draftModelSelectEl,
  draftProfileSelectEl,
  draftProviderSelectEl,
  draftTaskSelectEl,
  providerPillEl,
  renameSessionBtn,
} from '../dom.js';

export function setHeaderChrome() {
  const session = activeSession();
  const providerId = providerForUi();
  const modelId = modelForUi();
  const profileId = profileForUi();
  const taskModeId = taskModeForUi();
  const providerLabel = labelForProviderId(providerId);
  const modelLabel = labelForModel(providerId, modelId);
  const profileLabel = labelForProfile(profileId);
  const taskModeLabel = labelForTaskMode(taskModeId);

  providerPillEl.textContent = providerLabel;
  providerPillEl.title = 'Active runtime: ' + providerLabel;

  chatTitleEl.textContent = session ? sessionDisplayTitle(session) : 'New Chat';
  chatSubtitleEl.textContent = session ? (session.key || '') : 'Choose a runtime, model, and profile before your first message.';
  chatProviderBadgeEl.textContent = providerLabel;
  chatModelBadgeEl.textContent = modelLabel;
  chatProfileBadgeEl.textContent = profileLabel;
  chatModeBadgeEl.textContent = taskModeLabel;
  chatLockBadgeEl.textContent = session ? 'Locked Session' : 'Draft';
  draftConfigEl.classList.toggle('open', !session);

  renameSessionBtn.disabled = !session;
  archiveSessionBtn.disabled = !session;

  if (session) {
    composerBannerEl.textContent =
      'Replies will continue in "' + sessionDisplayTitle(session) + '" using ' +
      providerLabel + ' / ' + modelLabel + ' / ' + profileLabel + ' / ' + taskModeLabel + '.';
  } else {
    composerBannerEl.textContent =
      'This draft stays editable until the first message. After that, runtime, model, profile, and task mode lock.';
  }
}

export function syncProviderSelect() {
  draftProviderSelectEl.innerHTML = '';
  Object.keys(providerCatalog)
    .sort((a, b) => labelForProviderId(a).localeCompare(labelForProviderId(b)))
    .forEach((id) => {
      const row = providerCatalog[id];
      const opt = document.createElement('option');
      opt.value = id;
      opt.textContent = row.available === false ? labelForProviderId(id) + ' (unavailable)' : labelForProviderId(id);
      opt.disabled = row.available === false;
      draftProviderSelectEl.appendChild(opt);
    });

  const target = providerForUi();
  draftProviderSelectEl.value = providerCatalog[target] ? target : preferredProviderId();
  draftState.provider = draftProviderSelectEl.value || DEFAULT_CHAT_PROVIDER_ID;
}

export function syncModelSelect() {
  const providerId = providerForUi();
  const list = modelCatalog[providerId] || [];
  const targetModel = modelForUi();

  draftModelSelectEl.innerHTML = '';
  draftModelSelectEl.dataset.noModels = '0';

  if (!list.length) {
    const opt = document.createElement('option');
    opt.value = '';
    opt.textContent = providerId === 'codex-cli' ? 'Managed by provider' : 'No chat models available';
    draftModelSelectEl.appendChild(opt);
    draftModelSelectEl.dataset.noModels = '1';
    draftModelSelectEl.value = '';
    return;
  }

  list.forEach((model) => {
    const opt = document.createElement('option');
    opt.value = model.id;
    opt.textContent = model.description ? model.displayName + ' — ' + model.description : model.displayName;
    draftModelSelectEl.appendChild(opt);
  });

  if (targetModel && list.some((model) => model.id === targetModel)) {
    draftModelSelectEl.value = targetModel;
  } else {
    draftModelSelectEl.selectedIndex = 0;
  }

  if (isDraftMode()) {
    draftState.model = draftModelSelectEl.value || '';
  }
}

export function syncProfileSelect() {
  draftProfileSelectEl.innerHTML = '';
  Object.keys(profileCatalog).forEach((id) => {
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = profileCatalog[id].name;
    draftProfileSelectEl.appendChild(opt);
  });

  if (![...draftProfileSelectEl.options].some((opt) => opt.value === draftState.systemPromptId)) {
    draftState.systemPromptId = DEFAULT_PROFILE_ID;
  }
  draftProfileSelectEl.value = draftState.systemPromptId || DEFAULT_PROFILE_ID;
}

export function syncTaskModeSelect() {
  draftTaskSelectEl.innerHTML = '';
  Object.keys(taskModeCatalog).forEach((id) => {
    const opt = document.createElement('option');
    opt.value = id;
    opt.textContent = taskModeCatalog[id].name;
    draftTaskSelectEl.appendChild(opt);
  });

  if (![...draftTaskSelectEl.options].some((opt) => opt.value === draftState.taskPromptId)) {
    draftState.taskPromptId = taskModeCatalog[DEFAULT_TASK_MODE_ID] ? DEFAULT_TASK_MODE_ID : (Object.keys(taskModeCatalog)[0] || '');
  }
  draftTaskSelectEl.value = draftState.taskPromptId || DEFAULT_TASK_MODE_ID;
}
