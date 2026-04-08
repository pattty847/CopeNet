/**
 * render/sessions.js — session list DOM rendering.
 */

import {
  state,
  sessionCatalog,
  sessionsList,
  labelForProviderId,
  labelForModel,
  labelForProfile,
  labelForTaskMode,
  sessionDisplayTitle,
  formatTimestamp,
  DEFAULT_TASK_MODE_ID,
} from '../state.js';

/**
 * Re-render the full session list sidebar.
 * Imported by controllers/sessions.js after any catalog mutation.
 */
export function renderSessions() {
  const keys = Object.keys(sessionCatalog).sort((a, b) => {
    return String(sessionCatalog[b].updatedAt || '').localeCompare(String(sessionCatalog[a].updatedAt || ''));
  });

  sessionsList.innerHTML = '';
  if (!keys.length) {
    const empty = document.createElement('div');
    empty.className = 'session-updated';
    empty.textContent = 'No sessions yet.';
    sessionsList.appendChild(empty);
    return;
  }

  keys.forEach((key) => {
    const session = sessionCatalog[key];
    const el = document.createElement('div');
    el.className = 'session-item' + (key === state.currentSessionKey ? ' active' : '');
    // onclick wired in controllers/sessions.js via selectSession import
    el.dataset.sessionKey = key;

    const title = document.createElement('div');
    title.className = 'session-title';
    title.textContent = sessionDisplayTitle(session);
    el.appendChild(title);

    const keyEl = document.createElement('div');
    keyEl.className = 'session-key';
    keyEl.textContent = session.key || key;
    el.appendChild(keyEl);

    const meta = document.createElement('div');
    meta.className = 'session-meta';

    const provider = document.createElement('span');
    provider.className = 'mini-pill';
    provider.textContent = labelForProviderId(session.provider);
    meta.appendChild(provider);

    const model = document.createElement('span');
    model.className = 'mini-pill';
    model.textContent = labelForModel(session.provider, session.model);
    meta.appendChild(model);

    if (session.systemPromptId) {
      const profile = document.createElement('span');
      profile.className = 'mini-pill';
      profile.textContent = labelForProfile(session.systemPromptId);
      meta.appendChild(profile);
    }

    if (session.taskPromptId && session.taskPromptId !== DEFAULT_TASK_MODE_ID) {
      const taskMode = document.createElement('span');
      taskMode.className = 'mini-pill';
      taskMode.textContent = labelForTaskMode(session.taskPromptId);
      meta.appendChild(taskMode);
    }

    if (session.inFlightRunId) {
      const inflight = document.createElement('span');
      inflight.className = 'mini-pill';
      inflight.textContent = 'In Flight';
      meta.appendChild(inflight);
    }

    el.appendChild(meta);

    const updated = document.createElement('div');
    updated.className = 'session-updated';
    updated.textContent = formatTimestamp(session.updatedAt);
    el.appendChild(updated);

    sessionsList.appendChild(el);
  });
}
