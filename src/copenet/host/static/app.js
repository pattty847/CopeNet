(function () {
  const WS_URL = (location.protocol === 'https:' ? 'wss:' : 'ws:') + '//' + location.host + '/ws';
  const TOKEN = 'dev-token';

  let ws = null;
  let connected = false;
  let currentSessionKey = 'default';
  let activeRunId = null;

  const $ = (id) => document.getElementById(id);
  const statusEl = $('status');
  const sessionsList = $('sessions-list');
  const messagesEl = $('messages');
  const emptyState = $('empty-state');
  const errorBanner = $('error-banner');
  const promptPresetEl = $('prompt-preset');
  const inputEl = $('input');
  const sendBtn = $('send');

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

  function addMessage(role, content, isStreaming) {
    if (emptyState) emptyState.style.display = 'none';
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    const meta = document.createElement('div');
    meta.className = 'meta';
    meta.textContent = role === 'user' ? 'You' : 'Agent';
    div.appendChild(meta);
    const body = document.createElement('div');
    body.textContent = content || '';
    if (isStreaming) body.classList.add('streaming');
    div.appendChild(body);
    div.dataset.role = role;
    messagesEl.appendChild(div);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return body;
  }

  function uuid8() {
    return Math.random().toString(36).slice(2, 10);
  }

  function sendReq(method, params) {
    return new Promise((resolve, reject) => {
      if (!ws || ws.readyState !== WebSocket.OPEN) {
        reject(new Error('Not connected'));
        return;
      }
      const id = method + '-' + uuid8();
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

  function connect() {
    if (ws) try { ws.close(); } catch (_) {}
    setStatus('', 'Connecting…');
    hideError();
    ws = new WebSocket(WS_URL);

    ws.onopen = () => {
      // Wait for connect.challenge then send connect
    };

    ws.onmessage = (event) => {
      const frame = JSON.parse(event.data);

      if (frame.type === 'event' && frame.event === 'connect.challenge') {
        ws.send(JSON.stringify({
          type: 'req',
          id: 'connect-' + uuid8(),
          method: 'connect',
          params: { auth: { token: TOKEN } }
        }));
        return;
      }

      if (frame.type === 'res' && frame.id && frame.id.startsWith('connect-')) {
        if (frame.ok) {
          connected = true;
          setStatus('connected', 'Connected');
          loadPrompts();
          loadSessions();
          loadHistory();
        } else {
          connected = false;
          setStatus('error', 'Auth failed');
          showError(frame.error && frame.error.message || 'Connection failed');
        }
        return;
      }

      if (frame.type === 'event' && frame.event === 'chat') {
        const p = frame.payload || {};
        if (p.runId && activeRunId && p.runId !== activeRunId) return;
        if (p.runId) activeRunId = p.runId;
        const state = (p.state || '').toLowerCase();
        const msg = p.message;
        if (state === 'delta' && msg && msg.content) {
          const last = messagesEl.querySelector('.msg.assistant .streaming-body');
          if (last) last.textContent += msg.content;
          else {
            const body = addMessage('assistant', msg.content, true);
            body.classList.add('streaming-body');
          }
          messagesEl.scrollTop = messagesEl.scrollHeight;
        } else if (state === 'final' || state === 'error' || state === 'aborted') {
          const last = messagesEl.querySelector('.msg.assistant .streaming-body');
          if (last) last.classList.remove('streaming-body');
          if (state === 'error' && p.errorMessage) {
            const body = messagesEl.querySelector('.msg.assistant:last-of-type div:last-child');
            if (body) body.textContent += '\n[Error: ' + p.errorMessage + ']';
          }
          activeRunId = null;
        }
      }
    };

    ws.onclose = () => {
      connected = false;
      setStatus('error', 'Disconnected');
    };
    ws.onerror = () => setStatus('error', 'Error');
  }

  async function loadPrompts() {
    if (!promptPresetEl) return;
    try {
      const res = await sendReq('prompts.list', {});
      const prompts = res.prompts || [];
      promptPresetEl.innerHTML = '<option value="">None</option>';
      prompts.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name || p.id;
        if (p.id === 'default') opt.selected = true;
        promptPresetEl.appendChild(opt);
      });
      if (!promptPresetEl.querySelector('option[value="default"]') && prompts.length) {
        promptPresetEl.options[1].selected = true;
      }
    } catch (_) {}
  }

  async function loadSessions() {
    try {
      const res = await sendReq('sessions.list', {});
      const sessions = (res.sessions || []).map(s => s.key || s.sessionId || 'default');
      if (!sessions.length) sessions.push('default');
      sessionsList.innerHTML = '';
      const seen = new Set();
      sessions.forEach(key => {
        if (seen.has(key)) return;
        seen.add(key);
        const el = document.createElement('div');
        el.className = 'session-item' + (key === currentSessionKey ? ' active' : '');
        el.textContent = key;
        el.onclick = () => selectSession(key);
        sessionsList.appendChild(el);
      });
    } catch (_) {}
  }

  function selectSession(key) {
    currentSessionKey = key;
    document.querySelectorAll('.session-item').forEach(el => {
      el.classList.toggle('active', el.textContent === key);
    });
    loadHistory();
  }

  async function loadHistory() {
    try {
      const res = await sendReq('chat.history', { sessionKey: currentSessionKey, limit: 100 });
      const list = res.messages || [];
      // Keep empty state and streaming placeholder logic; render history
      const toKeep = messagesEl.querySelectorAll('.msg.streaming-body');
      messagesEl.innerHTML = '';
      if (emptyState) {
        messagesEl.appendChild(emptyState);
        emptyState.style.display = list.length ? 'none' : 'block';
      }
      list.forEach(m => {
        const role = (m.role || 'user').toLowerCase();
        const content = typeof m.content === 'string' ? m.content : (m.content && m.content.text) || '';
        addMessage(role, content, false);
      });
      toKeep.forEach(n => messagesEl.appendChild(n));
      messagesEl.scrollTop = messagesEl.scrollHeight;
    } catch (_) {
      if (emptyState) emptyState.style.display = 'block';
    }
  }

  async function sendMessage() {
    const text = (inputEl.value || '').trim();
    if (!text || !connected) return;
    inputEl.value = '';
    addMessage('user', text, false);
    activeRunId = null;
    const idem = 'send-' + uuid8();
    const systemPromptId = (promptPresetEl && promptPresetEl.value) ? promptPresetEl.value : '';
    const params = {
      sessionKey: currentSessionKey,
      message: text,
      idempotencyKey: idem,
      provider: 'codex-cli'
    };
    if (systemPromptId) params.systemPromptId = systemPromptId;
    try {
      ws.send(JSON.stringify({
        type: 'req',
        id: idem,
        method: 'chat.send',
        params
      }));
    } catch (e) {
      showError(e.message);
    }
  }

  sendBtn.addEventListener('click', sendMessage);
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  connect();
})();
