/**
 * controllers/chat.js — WebSocket connection, send/receive lifecycle, and bootstrap.
 */

import {
  state,
  draftState,
  sessionCatalog,
  chatSendAckTimers,
  chatSendAckHandlers,
  activeSession,
  providerForUi,
  modelForUi,
} from '../state.js';
import { inputEl, messagesEl, sendBtn } from '../dom.js';
import { WS_URL, getAuthToken } from '../auth.js';
import {
  setStatus,
  showError,
  hideError,
  setSendingBusy,
  addMessage,
  addAgentErrorMessage,
  showPendingIndicator,
  removePendingIndicator,
  setAssistantBodyContent,
  setToolTraceContent,
  describeError,
  logClientError,
} from '../render/messages.js';
import { setHeaderChrome } from '../render/header.js';
import {
  loadProviders,
  loadPrompts,
  loadSessions,
  selectSession,
  beginDraft,
  createSessionFromDraft,
  scheduleSessionRefresh,
} from './sessions.js';

// ---------------------------------------------------------------------------
// Chat send acknowledgement handlers
// ---------------------------------------------------------------------------

export function clearChatSendAck(reqId) {
  const t = chatSendAckTimers[reqId];
  if (t) clearTimeout(t);
  delete chatSendAckTimers[reqId];
  delete chatSendAckHandlers[reqId];
}

export function registerChatSendAckHandler(reqId) {
  clearChatSendAck(reqId);
  chatSendAckHandlers[reqId] = (frame) => {
    if (!frame.ok) {
      clearChatSendAck(reqId);
      removePendingIndicator();
      addAgentErrorMessage((frame.error && frame.error.message) || 'Request failed');
      setSendingBusy(false);
      state.activeRunId = null;
      return;
    }
    const payload = frame.payload || {};
    const status = payload.status || '';
    if (status === 'in_flight') {
      clearChatSendAck(reqId);
      removePendingIndicator();
      addAgentErrorMessage('This session already has a reply in progress. Wait for it to finish or start another session.');
      setSendingBusy(false);
      state.activeRunId = null;
      return;
    }
    if (status === 'started') {
      if (payload.runId) state.activeRunId = payload.runId;
      if (chatSendAckTimers[reqId]) clearTimeout(chatSendAckTimers[reqId]);
      chatSendAckTimers[reqId] = setTimeout(() => clearChatSendAck(reqId), 500);
    }
  };
}

// ---------------------------------------------------------------------------
// Send message
// ---------------------------------------------------------------------------

export async function sendMessage() {
  const text = (inputEl.value || '').trim();
  if (!text || !state.connected || sendBtn.disabled) return;

  hideError();

  try {
    if (!activeSession()) {
      await createSessionFromDraft();
    }
  } catch (err) {
    showError(err.message || 'Unable to create session.');
    return;
  }

  const session = activeSession();
  if (!session) return;

  inputEl.value = '';
  addMessage('user', text, false, null);
  state.activeRunId = null;

  const idem = 'send-' + Math.random().toString(36).slice(2, 10);
  const params = {
    sessionKey: session.key,
    message: text,
    idempotencyKey: idem,
    provider: session.provider,
    model: session.model,
  };
  if (session.systemPromptId) params.systemPromptId = session.systemPromptId;
  if (session.taskPromptId) params.taskPromptId = session.taskPromptId;

  showPendingIndicator({ provider: session.provider, model: session.model });
  setSendingBusy(true);
  registerChatSendAckHandler(idem);

  try {
    state.ws.send(JSON.stringify({ type: 'req', id: idem, method: 'chat.send', params }));
  } catch (err) {
    clearChatSendAck(idem);
    removePendingIndicator();
    addAgentErrorMessage(err.message || 'Failed to send message.');
    setSendingBusy(false);
  }
}

// ---------------------------------------------------------------------------
// Bootstrap (runs once after auth)
// ---------------------------------------------------------------------------

export async function bootstrap() {
  await loadProviders();
  await Promise.all([loadPrompts(), loadSessions()]);

  const firstSessionKey = Object.keys(sessionCatalog).sort((a, b) => {
    return String(sessionCatalog[b].updatedAt || '').localeCompare(String(sessionCatalog[a].updatedAt || ''));
  })[0] || null;

  if (firstSessionKey) {
    await selectSession(firstSessionKey);
  } else {
    await beginDraft({});
  }

  state.bootstrapped = true;
}

// ---------------------------------------------------------------------------
// WebSocket connection and event loop
// ---------------------------------------------------------------------------

export function connect() {
  if (state.ws) {
    try {
      state.ws.close();
    } catch (err) {
      logClientError('websocket close failed', err);
    }
  }
  Object.keys(chatSendAckHandlers).forEach(clearChatSendAck);
  removePendingIndicator();
  setSendingBusy(false);
  setStatus('', 'Connecting…');
  hideError();
  state.ws = new WebSocket(WS_URL);

  state.ws.onmessage = async (event) => {
    const frame = JSON.parse(event.data);

    if (frame.type === 'res' && frame.id && chatSendAckHandlers[frame.id]) {
      chatSendAckHandlers[frame.id](frame);
      return;
    }

    if (frame.type === 'event' && frame.event === 'connect.challenge') {
      state.ws.send(JSON.stringify({
        type: 'req',
        id: 'connect-' + Math.random().toString(36).slice(2, 10),
        method: 'connect',
        params: { auth: { token: getAuthToken() } },
      }));
      return;
    }

    if (frame.type === 'res' && frame.id && frame.id.startsWith('connect-')) {
      if (frame.ok) {
        state.connected = true;
        setStatus('connected', 'Connected');
        try {
          await bootstrap();
        } catch (err) {
          logClientError('bootstrap failed', err);
          showError(describeError(err, 'Bootstrap failed'));
        }
      } else {
        state.connected = false;
        setStatus('error', 'Auth failed');
        showError((frame.error && frame.error.message) || 'Connection failed');
      }
      return;
    }

    if (frame.type === 'event' && frame.event === 'chat') {
      const payload = frame.payload || {};
      if (payload.runId && state.activeRunId && payload.runId !== state.activeRunId) return;
      if (payload.runId) state.activeRunId = payload.runId;

      const chatState = (payload.state || '').toLowerCase();
      const meta = {
        provider: payload.provider || (payload.message && payload.message.provider) || providerForUi(),
        model: payload.model || (payload.message && payload.message.model) || modelForUi(),
        toolExecution: payload.toolExecution || null,
      };
      const msg = payload.message;

      if (chatState === 'delta' && msg && msg.content) {
        removePendingIndicator();
        const last = messagesEl.querySelector('.msg.assistant .streaming-body');
        if (last) {
          const nextText = (last.dataset.rawText || '') + msg.content;
          last.dataset.rawText = nextText;
          setAssistantBodyContent(last, nextText);
          const root = last.closest('.msg.assistant');
          if (root) {
            setToolTraceContent(root.querySelector('.tool-trace-wrap'), payload.toolExecution || null);
          }
        } else {
          const parts = addMessage('assistant', msg.content, true, meta);
          parts.body.dataset.rawText = msg.content;
        }
        messagesEl.scrollTop = messagesEl.scrollHeight;
      } else if (chatState === 'final' || chatState === 'error' || chatState === 'aborted') {
        removePendingIndicator();
        const last = messagesEl.querySelector('.msg.assistant .streaming-body');
        if (last) {
          last.classList.remove('streaming-body');
          const root = last.closest('.msg.assistant');
          if (root) {
            setToolTraceContent(root.querySelector('.tool-trace-wrap'), payload.toolExecution || null);
          }
        }
        if (chatState === 'error') {
          addAgentErrorMessage(payload.errorMessage || 'The agent run failed.');
        }
        state.activeRunId = null;
        setSendingBusy(false);
        if (state.currentSessionKey && state.bootstrapped) {
          try {
            await loadSessions();
            if (sessionCatalog[state.currentSessionKey]) await selectSession(state.currentSessionKey);
            scheduleSessionRefresh();
          } catch (err) {
            logClientError('session reload after chat failed', err);
          }
        }
      }
    }
  };

  state.ws.onclose = () => {
    state.connected = false;
    setStatus('error', 'Disconnected');
    Object.keys(chatSendAckHandlers).forEach(clearChatSendAck);
    removePendingIndicator();
    setSendingBusy(false);
    state.activeRunId = null;
  };

  state.ws.onerror = () => setStatus('error', 'Error');
}
