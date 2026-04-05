(function () {
  const WS_URL = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws';
  const TOKEN = 'dev-token';
  const DEFAULT_CHAT_PROVIDER_ID = 'codex-cli';
  const DEFAULT_PROFILE_ID = 'default';
  const DEFAULT_TASK_MODE_ID = 'none';

  let ws = null;
  let connected = false;
  let currentSessionKey = null;
  let activeRunId = null;
  let pendingIndicatorEl = null;
  let bootstrapped = false;
  const chatSendAckTimers = {};
  const chatSendAckHandlers = {};
  const sessionCatalog = {};

  const draftState = {
    provider: DEFAULT_CHAT_PROVIDER_ID,
    model: '',
    systemPromptId: DEFAULT_PROFILE_ID,
    taskPromptId: DEFAULT_TASK_MODE_ID
  };

  const $ = (id) => document.getElementById(id);
  const statusEl = $('status');
  const sessionsList = $('sessions-list');
  const messagesEl = $('messages');
  const emptyState = $('empty-state');
  const errorBanner = $('error-banner');
  const composerBannerEl = $('composer-banner');
  const chatTitleEl = $('chat-title');
  const chatSubtitleEl = $('chat-subtitle');
  const chatProviderBadgeEl = $('chat-provider-badge');
  const chatModelBadgeEl = $('chat-model-badge');
  const chatProfileBadgeEl = $('chat-profile-badge');
  const chatModeBadgeEl = $('chat-mode-badge');
  const chatLockBadgeEl = $('chat-lock-badge');
  const draftConfigEl = $('draft-config');
  const draftProviderSelectEl = $('draft-provider-select');
  const draftModelSelectEl = $('draft-model-select');
  const draftProfileSelectEl = $('draft-profile-select');
  const draftTaskSelectEl = $('draft-task-select');
  const promptSettingsBtn = $('prompt-settings');
  const renameSessionBtn = $('rename-session');
  const archiveSessionBtn = $('archive-session');
  const newChatBtn = $('new-chat');
  const inputEl = $('input');
  const sendBtn = $('send');
  const providerPillEl = $('provider-pill');

  /** @type {Record<string, { displayName: string, available: boolean, error: string, capabilities?: Record<string, boolean>, defaultModel?: string }>} */
  const providerCatalog = {};
  /** @type {Record<string, Array<{id: string, displayName: string, provider: string, description?: string, kind?: string}>>} */
  const modelCatalog = {};
  /** @type {Record<string, { id: string, name: string }>} */
  const profileCatalog = {};
  const taskModeCatalog = {};

  function activeSession() {
    return currentSessionKey ? sessionCatalog[currentSessionKey] || null : null;
  }

  function isDraftMode() {
    return !activeSession();
  }

  function sessionDisplayTitle(session) {
    if (!session) return 'New Chat';
    return (session.title || '').trim() || session.key || 'Untitled Session';
  }

  function labelForProviderId(id) {
    if (!id) return 'Assistant';
    const row = providerCatalog[id];
    if (row && row.displayName) return row.displayName;
    return String(id)
      .split(/[-_]/)
      .filter(Boolean)
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
      .join(' ');
  }

  function labelForModel(providerId, modelId) {
    if (!modelId) {
      return providerId === 'codex-cli' ? 'Managed by provider' : 'No model selected';
    }
    const list = modelCatalog[providerId] || [];
    const row = list.find((item) => item.id === modelId);
    return row ? row.displayName : modelId;
  }

  function labelForProfile(promptId) {
    if (!promptId) return 'None';
    const row = profileCatalog[promptId];
    return row ? row.name : promptId;
  }

  function labelForTaskMode(taskPromptId) {
    if (!taskPromptId || taskPromptId === DEFAULT_TASK_MODE_ID) return 'General';
    const row = taskModeCatalog[taskPromptId];
    return row ? row.name : taskPromptId;
  }

  function providerForUi() {
    const session = activeSession();
    return (session && session.provider) || draftState.provider || DEFAULT_CHAT_PROVIDER_ID;
  }

  function modelForUi() {
    const session = activeSession();
    return (session && session.model) || draftState.model || '';
  }

  function profileForUi() {
    const session = activeSession();
    return (session && session.systemPromptId) || draftState.systemPromptId || DEFAULT_PROFILE_ID;
  }

  function taskModeForUi() {
    const session = activeSession();
    return (session && session.taskPromptId) || draftState.taskPromptId || DEFAULT_TASK_MODE_ID;
  }

  function preferredProviderId() {
    const ranked = ['lm-studio', 'ollama', 'codex-cli'];
    for (const id of ranked) {
      const row = providerCatalog[id];
      if (row && row.available !== false) return id;
    }
    return ranked.find((id) => providerCatalog[id]) || DEFAULT_CHAT_PROVIDER_ID;
  }

  function formatTimestamp(iso) {
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

  function setStatus(className, text) {
    statusEl.className = 'status ' + (className || '');
    statusEl.textContent = text || (connected ? 'Connected' : 'Disconnected');
  }

  function showError(msg) {
    errorBanner.textContent = msg;
    errorBanner.style.display = 'block';
  }

  function hideError() {
    errorBanner.style.display = 'none';
  }

  function setSendingBusy(busy) {
    sendBtn.disabled = !!busy;
    inputEl.disabled = !!busy;
    if (connected) {
      setStatus('connected', busy ? 'Waiting for reply…' : 'Connected');
    }
  }

  function clearChatSendAck(reqId) {
    const t = chatSendAckTimers[reqId];
    if (t) clearTimeout(t);
    delete chatSendAckTimers[reqId];
    delete chatSendAckHandlers[reqId];
  }

  function setHeaderChrome() {
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

  function syncProviderSelect() {
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

  function syncModelSelect() {
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

  function syncProfileSelect() {
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

  function syncTaskModeSelect() {
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

  function renderSessions() {
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
      el.className = 'session-item' + (key === currentSessionKey ? ' active' : '');
      el.onclick = () => selectSession(key);

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

  function addMetaLabel(meta) {
    if (!meta) return 'Assistant';
    const provider = meta.provider ? labelForProviderId(meta.provider) : 'Assistant';
    const model = meta.model ? labelForModel(meta.provider, meta.model) : '';
    return model ? provider + ' · ' + model : provider;
  }

  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function isLikelyMathLine(line) {
    const text = String(line || '').trim();
    if (!text) return false;
    if (/^```/.test(text)) return false;
    if (/^[-*+] /.test(text) || /^\d+\. /.test(text)) return false;
    if (/^#{1,6}\s/.test(text) || /^>/.test(text)) return false;
    if (/[.?!]$/.test(text) && !/=/.test(text)) return false;
    if (/^\$\$.*\$\$$/.test(text) || /^\\\[.*\\\]$/.test(text) || /^\\\(.*\\\)$/.test(text)) return false;

    const hasMathSignal =
      /[=+\-*/^_]/.test(text) ||
      /[α-ωΑ-ΩνωλμΔΣπ]/u.test(text) ||
      /\\[a-zA-Z]+/.test(text);

    const looksCompact = text.length <= 80 && /^[A-Za-z0-9\s_=+\-*/^_(){}\[\]\\.,;:α-ωΑ-ΩνωλμΔΣπ]+$/u.test(text);
    return hasMathSignal && looksCompact;
  }

  function preprocessAssistantMarkdown(raw) {
    const lines = String(raw || '').split('\n');
    const output = [];
    let inCodeFence = false;
    let mathBuffer = [];

    const flushMath = () => {
      if (!mathBuffer.length) return;
      if (mathBuffer.length === 1) {
        output.push('$$' + mathBuffer[0].trim() + '$$');
      } else {
        output.push('$$' + mathBuffer.map((line) => line.trim()).join(' ') + '$$');
      }
      mathBuffer = [];
    };

    for (const line of lines) {
      const trimmed = line.trim();
      if (/^```/.test(trimmed)) {
        flushMath();
        inCodeFence = !inCodeFence;
        output.push(line);
        continue;
      }
      if (inCodeFence) {
        output.push(line);
        continue;
      }
      if (isLikelyMathLine(line)) {
        mathBuffer.push(line);
        continue;
      }
      flushMath();
      output.push(line);
    }

    flushMath();
    return output.join('\n');
  }

  function renderMathInElement(root) {
    const katexApi = window.katex;
    if (!root || !katexApi) return;

    const walk = (node) => {
      if (!node) return;
      if (node.nodeType === Node.TEXT_NODE) {
        const text = node.textContent || '';
        if (!text.includes('$') && !text.includes('\\(') && !text.includes('\\[')) return;

        const fragment = document.createDocumentFragment();
        const pattern = /(\$\$[\s\S]+?\$\$|\\\[[\s\S]+?\\\]|\\\([\s\S]+?\\\)|\$[^$\n]+\$)/g;
        let lastIndex = 0;
        let matched = false;
        let match;

        while ((match = pattern.exec(text)) !== null) {
          matched = true;
          if (match.index > lastIndex) {
            fragment.appendChild(document.createTextNode(text.slice(lastIndex, match.index)));
          }

          const token = match[0];
          const displayMode = token.startsWith('$$') || token.startsWith('\\[');
          let expr = token;
          if (token.startsWith('$$')) expr = token.slice(2, -2);
          else if (token.startsWith('\\[')) expr = token.slice(2, -2);
          else if (token.startsWith('\\(')) expr = token.slice(2, -2);
          else expr = token.slice(1, -1);
          const span = document.createElement(displayMode ? 'div' : 'span');
          try {
            katexApi.render(expr, span, { throwOnError: false, displayMode });
            fragment.appendChild(span);
          } catch (_) {
            fragment.appendChild(document.createTextNode(token));
          }
          lastIndex = match.index + token.length;
        }

        if (!matched) return;
        if (lastIndex < text.length) {
          fragment.appendChild(document.createTextNode(text.slice(lastIndex)));
        }
        node.parentNode.replaceChild(fragment, node);
        return;
      }

      if (node.nodeType !== Node.ELEMENT_NODE) return;
      const tag = node.tagName;
      if (tag === 'CODE' || tag === 'PRE' || node.classList.contains('katex')) return;
      Array.from(node.childNodes).forEach(walk);
    };

    walk(root);
  }

  function setAssistantBodyContent(body, content) {
    const raw = String(content || '');
    body.classList.add('rendered-content');
    const prepared = preprocessAssistantMarkdown(raw);

    try {
      if (window.marked && window.DOMPurify) {
        const html = window.marked.parse(prepared, { breaks: true, gfm: true });
        body.innerHTML = window.DOMPurify.sanitize(html);
        renderMathInElement(body);
        return;
      }
    } catch (_) {}

    body.innerHTML = '<p>' + escapeHtml(prepared).replace(/\n/g, '<br />') + '</p>';
  }

  function addMessage(role, content, isStreaming, meta) {
    if (emptyState) emptyState.style.display = 'none';
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    const metaEl = document.createElement('div');
    metaEl.className = 'meta';
    metaEl.textContent = role === 'user' ? 'You' : addMetaLabel(meta);
    div.appendChild(metaEl);
    const body = document.createElement('div');
    if (role === 'assistant') {
      setAssistantBodyContent(body, content || '');
    } else {
      body.textContent = content || '';
    }
    if (isStreaming) body.classList.add('streaming-body');
    div.appendChild(body);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return body;
  }

  function showPendingIndicator(meta) {
    removePendingIndicator();
    if (emptyState) emptyState.style.display = 'none';
    const div = document.createElement('div');
    div.className = 'msg assistant pending';
    const metaEl = document.createElement('div');
    metaEl.className = 'meta';
    metaEl.textContent = addMetaLabel(meta);
    div.appendChild(metaEl);
    const wrap = document.createElement('div');
    wrap.className = 'body-pending';
    wrap.appendChild(document.createTextNode('Thinking'));
    const dots = document.createElement('span');
    dots.className = 'pending-dots';
    dots.appendChild(document.createElement('span'));
    dots.appendChild(document.createElement('span'));
    dots.appendChild(document.createElement('span'));
    wrap.appendChild(dots);
    div.appendChild(wrap);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    pendingIndicatorEl = div;
  }

  function removePendingIndicator() {
    if (pendingIndicatorEl && pendingIndicatorEl.parentNode) {
      pendingIndicatorEl.parentNode.removeChild(pendingIndicatorEl);
    }
    pendingIndicatorEl = null;
  }

  function addAgentErrorMessage(text) {
    if (emptyState) emptyState.style.display = 'none';
    const div = document.createElement('div');
    div.className = 'msg agent-error';
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = 'Error';
    div.appendChild(meta);
    const body = document.createElement('div');
    body.textContent = text || 'Something went wrong.';
    div.appendChild(body);
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function registerChatSendAckHandler(reqId) {
    clearChatSendAck(reqId);
    chatSendAckHandlers[reqId] = (frame) => {
      if (!frame.ok) {
        clearChatSendAck(reqId);
        removePendingIndicator();
        addAgentErrorMessage((frame.error && frame.error.message) || 'Request failed');
        setSendingBusy(false);
        activeRunId = null;
        return;
      }
      const payload = frame.payload || {};
      const status = payload.status || '';
      if (status === 'in_flight') {
        clearChatSendAck(reqId);
        removePendingIndicator();
        addAgentErrorMessage('This session already has a reply in progress. Wait for it to finish or start another session.');
        setSendingBusy(false);
        activeRunId = null;
        return;
      }
      if (status === 'started') {
        if (payload.runId) activeRunId = payload.runId;
        if (chatSendAckTimers[reqId]) clearTimeout(chatSendAckTimers[reqId]);
        chatSendAckTimers[reqId] = setTimeout(() => clearChatSendAck(reqId), 500);
      }
    };
  }

  function sendReq(method, params) {
    return new Promise((resolve, reject) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        reject(new Error('Not connected'));
        return;
      }
      const id = method + '-' + Math.random().toString(36).slice(2, 10);
      ws.send(JSON.stringify({ type: 'req', id, method, params }));

      const onMessage = (e) => {
        const frame = JSON.parse(e.data);
        if (frame.type === 'res' && frame.id === id) {
          ws.removeEventListener('message', onMessage);
          if (frame.ok) resolve(frame.payload || {});
          else reject(new Error((frame.error && frame.error.message) || 'RPC error'));
        }
      };
      ws.addEventListener('message', onMessage);
    });
  }

  async function loadProviders() {
    const res = await sendReq('providers.list', {});
    Object.keys(providerCatalog).forEach((key) => delete providerCatalog[key]);
    (res.providers || []).forEach((provider) => {
      providerCatalog[provider.id] = {
        displayName: provider.displayName || provider.id,
        available: provider.available !== false,
        error: provider.error || '',
        capabilities: provider.capabilities || {},
        defaultModel: provider.defaultModel || ''
      };
    });
    if (!providerCatalog[draftState.provider] || providerCatalog[draftState.provider].available === false) {
      draftState.provider = preferredProviderId();
    }
    syncProviderSelect();
  }

  async function loadModels(providerId) {
    if (!providerId) return;
    try {
      const res = await sendReq('models.list', { provider: providerId, kind: 'chat' });
      modelCatalog[providerId] = (res.models || []).filter((model) => model.provider === providerId);
    } catch (_) {
      modelCatalog[providerId] = [];
    }

    if (isDraftMode()) {
      const list = modelCatalog[providerId] || [];
      if (!draftState.model || !list.some((item) => item.id === draftState.model)) {
        const provider = providerCatalog[providerId];
        draftState.model = provider && provider.defaultModel ? provider.defaultModel : ((list[0] && list[0].id) || '');
      }
    }

    syncModelSelect();
    setHeaderChrome();
  }

  async function loadPrompts() {
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

  async function loadSessions() {
    const res = await sendReq('sessions.list', {});
    Object.keys(sessionCatalog).forEach((key) => delete sessionCatalog[key]);
    (res.sessions || []).forEach((session) => {
      sessionCatalog[session.key || session.sessionId] = session;
    });
    renderSessions();
  }

  async function loadHistory() {
    if (!currentSessionKey) {
      messagesEl.innerHTML = '';
      if (emptyState) {
        messagesEl.appendChild(emptyState);
        emptyState.style.display = 'block';
      }
      return;
    }

    try {
      const res = await sendReq('chat.history', { sessionKey: currentSessionKey, limit: 100 });
      const list = res.messages || [];
      messagesEl.innerHTML = '';
      if (emptyState) {
        messagesEl.appendChild(emptyState);
        emptyState.style.display = list.length ? 'none' : 'block';
      }
      list.forEach((message) => {
        const role = (message.role || 'user').toLowerCase();
        const content = typeof message.content === 'string' ? message.content : (message.content && message.content.text) || '';
        addMessage(role, content, false, role === 'assistant' ? { provider: message.provider, model: message.model } : null);
      });
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } catch (_) {
      if (emptyState) emptyState.style.display = 'block';
    }
  }

  async function selectSession(key) {
    currentSessionKey = key;
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

  async function beginDraft(preferred) {
    currentSessionKey = null;
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

  async function createSessionFromDraft() {
    const provider = draftProviderSelectEl.value || draftState.provider || preferredProviderId();
    const model = draftModelSelectEl.dataset.noModels === '1' ? null : (draftModelSelectEl.value || null);
    const systemPromptId = draftProfileSelectEl.value || draftState.systemPromptId || undefined;
    const taskPromptId = draftTaskSelectEl.value || draftState.taskPromptId || undefined;

    if (!provider) {
      throw new Error('Choose a runtime first.');
    }

    const res = await sendReq('sessions.create', {
      provider,
      model,
      systemPromptId,
      taskPromptId
    });
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

  async function renameCurrentSession() {
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

  async function archiveCurrentSession() {
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
        taskPromptId: session.taskPromptId
      });
    }
  }

  function scheduleSessionRefresh() {
    if (!currentSessionKey) return;
    const key = currentSessionKey;
    [1200, 2600, 4200].forEach((delayMs) => {
      setTimeout(async () => {
        if (currentSessionKey !== key) return;
        try {
          await loadSessions();
          if (sessionCatalog[key]) await selectSession(key);
        } catch (_) {}
      }, delayMs);
    });
  }

  async function sendMessage() {
    const text = (inputEl.value || '').trim();
    if (!text || !connected || sendBtn.disabled) return;

    hideError();

    try {
      if (isDraftMode()) {
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
    activeRunId = null;

    const idem = 'send-' + Math.random().toString(36).slice(2, 10);
    const params = {
      sessionKey: session.key,
      message: text,
      idempotencyKey: idem,
      provider: session.provider,
      model: session.model
    };
    if (session.systemPromptId) params.systemPromptId = session.systemPromptId;
    if (session.taskPromptId) params.taskPromptId = session.taskPromptId;

    showPendingIndicator({ provider: session.provider, model: session.model });
    setSendingBusy(true);
    registerChatSendAckHandler(idem);

    try {
      ws.send(JSON.stringify({
        type: 'req',
        id: idem,
        method: 'chat.send',
        params
      }));
    } catch (err) {
      clearChatSendAck(idem);
      removePendingIndicator();
      addAgentErrorMessage(err.message || 'Failed to send message.');
      setSendingBusy(false);
    }
  }

  async function bootstrap() {
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

    bootstrapped = true;
  }

  function connect() {
    if (ws) {
      try { ws.close(); } catch (_) {}
    }
    Object.keys(chatSendAckHandlers).forEach(clearChatSendAck);
    removePendingIndicator();
    setSendingBusy(false);
    setStatus('', 'Connecting…');
    hideError();
    ws = new WebSocket(WS_URL);

    ws.onmessage = async (event) => {
      const frame = JSON.parse(event.data);

      if (frame.type === 'res' && frame.id && chatSendAckHandlers[frame.id]) {
        chatSendAckHandlers[frame.id](frame);
        return;
      }

      if (frame.type === 'event' && frame.event === 'connect.challenge') {
        ws.send(JSON.stringify({
          type: 'req',
          id: 'connect-' + Math.random().toString(36).slice(2, 10),
          method: 'connect',
          params: { auth: { token: TOKEN } }
        }));
        return;
      }

      if (frame.type === 'res' && frame.id && frame.id.startsWith('connect-')) {
        if (frame.ok) {
          connected = true;
          setStatus('connected', 'Connected');
          try {
            await bootstrap();
          } catch (err) {
            showError(err.message || 'Bootstrap failed');
          }
        } else {
          connected = false;
          setStatus('error', 'Auth failed');
          showError((frame.error && frame.error.message) || 'Connection failed');
        }
        return;
      }

      if (frame.type === 'event' && frame.event === 'chat') {
        const payload = frame.payload || {};
        if (payload.runId && activeRunId && payload.runId !== activeRunId) return;
        if (payload.runId) activeRunId = payload.runId;

        const state = (payload.state || '').toLowerCase();
        const meta = {
          provider: payload.provider || (payload.message && payload.message.provider) || providerForUi(),
          model: payload.model || (payload.message && payload.message.model) || modelForUi()
        };
        const msg = payload.message;

        if (state === 'delta' && msg && msg.content) {
          removePendingIndicator();
          const last = messagesEl.querySelector('.msg.assistant .streaming-body');
          if (last) {
            const nextText = (last.dataset.rawText || '') + msg.content;
            last.dataset.rawText = nextText;
            setAssistantBodyContent(last, nextText);
          } else {
            const body = addMessage('assistant', msg.content, true, meta);
            body.dataset.rawText = msg.content;
          }
          messagesEl.scrollTop = messagesEl.scrollHeight;
        } else if (state === 'final' || state === 'error' || state === 'aborted') {
          removePendingIndicator();
          const last = messagesEl.querySelector('.msg.assistant .streaming-body');
          if (last) last.classList.remove('streaming-body');
          if (state === 'error') {
            addAgentErrorMessage(payload.errorMessage || 'The agent run failed.');
          }
          activeRunId = null;
          setSendingBusy(false);
          if (currentSessionKey && bootstrapped) {
            try {
              await loadSessions();
              if (sessionCatalog[currentSessionKey]) await selectSession(currentSessionKey);
              scheduleSessionRefresh();
            } catch (_) {}
          }
        }
      }
    };

    ws.onclose = () => {
      connected = false;
      setStatus('error', 'Disconnected');
      Object.keys(chatSendAckHandlers).forEach(clearChatSendAck);
      removePendingIndicator();
      setSendingBusy(false);
      activeRunId = null;
    };

    ws.onerror = () => setStatus('error', 'Error');
  }

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

  sendBtn.addEventListener('click', sendMessage);
  newChatBtn.addEventListener('click', () => {
    hideError();
    beginDraft({
      provider: providerForUi(),
      model: modelForUi(),
      systemPromptId: profileForUi(),
      taskPromptId: taskModeForUi()
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

  connect();
})();
