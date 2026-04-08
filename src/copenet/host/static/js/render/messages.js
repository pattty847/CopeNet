/**
 * render/messages.js — message DOM, markdown/math rendering, status helpers.
 */

import {
  state,
  messagesEl,
  emptyState,
  errorBanner,
  statusEl,
  sendBtn,
  inputEl,
  labelForProviderId,
  labelForModel,
} from '../state.js';

// ---------------------------------------------------------------------------
// Status / error helpers
// ---------------------------------------------------------------------------

export function setStatus(className, text) {
  statusEl.className = 'status ' + (className || '');
  statusEl.textContent = text || (state.connected ? 'Connected' : 'Disconnected');
}

export function showError(msg) {
  errorBanner.textContent = msg;
  errorBanner.style.display = 'block';
}

export function hideError() {
  errorBanner.style.display = 'none';
}

export function setSendingBusy(busy) {
  sendBtn.disabled = !!busy;
  inputEl.disabled = !!busy;
  if (state.connected) {
    setStatus('connected', busy ? 'Waiting for reply…' : 'Connected');
  }
}

// ---------------------------------------------------------------------------
// Math / markdown rendering
// ---------------------------------------------------------------------------

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

export function escapeHtml(value) {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function setAssistantBodyContent(body, content) {
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

export function setToolTraceContent(container, toolExecution) {
  if (!container) return;
  container.innerHTML = '';
  if (!toolExecution || typeof toolExecution !== 'object') {
    container.style.display = 'none';
    return;
  }
  container.style.display = '';

  const details = document.createElement('details');
  details.className = 'tool-trace';

  const summary = document.createElement('summary');
  const summaryLabel = document.createElement('span');
  const toolId = toolExecution.toolId || 'tool';
  const status = toolExecution.ok === false ? 'error' : 'ok';
  summaryLabel.textContent = 'Tool Call · ' + toolId;
  summary.appendChild(summaryLabel);
  details.appendChild(summary);

  const body = document.createElement('div');
  body.className = 'tool-trace-body';

  const row = document.createElement('div');
  row.className = 'tool-trace-row';

  const toolPill = document.createElement('span');
  toolPill.className = 'tool-trace-code';
  toolPill.textContent = toolId;
  row.appendChild(toolPill);

  const statusPill = document.createElement('span');
  statusPill.className = status === 'ok' ? 'tool-trace-ok' : 'tool-trace-error';
  statusPill.textContent = status === 'ok' ? 'Success' : 'Error';
  row.appendChild(statusPill);
  body.appendChild(row);

  if (toolExecution.summary) {
    const summaryText = document.createElement('div');
    summaryText.className = 'tool-trace-summary';
    summaryText.textContent = toolExecution.summary;
    body.appendChild(summaryText);
  }

  if (toolExecution.error) {
    const errorText = document.createElement('div');
    errorText.className = 'tool-trace-error-text';
    errorText.textContent = toolExecution.error;
    body.appendChild(errorText);
  }

  details.appendChild(body);
  container.appendChild(details);
}

// ---------------------------------------------------------------------------
// Message DOM builders
// ---------------------------------------------------------------------------

export function addMetaLabel(meta) {
  if (!meta) return 'Assistant';
  const provider = meta.provider ? labelForProviderId(meta.provider) : 'Assistant';
  const model = meta.model ? labelForModel(meta.provider, meta.model) : '';
  return model ? provider + ' · ' + model : provider;
}

export function addMessage(role, content, isStreaming, meta) {
  if (emptyState) emptyState.style.display = 'none';
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  const metaEl = document.createElement('div');
  metaEl.className = 'meta';
  metaEl.textContent = role === 'user' ? 'You' : addMetaLabel(meta);
  div.appendChild(metaEl);
  let toolTraceEl = null;
  if (role === 'assistant') {
    toolTraceEl = document.createElement('div');
    toolTraceEl.className = 'tool-trace-wrap';
    toolTraceEl.style.display = 'none';
    div.appendChild(toolTraceEl);
    setToolTraceContent(toolTraceEl, meta && meta.toolExecution);
  }
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
  return { body, toolTraceEl, root: div };
}

export function showPendingIndicator(meta) {
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
  state.pendingIndicatorEl = div;
}

export function removePendingIndicator() {
  if (state.pendingIndicatorEl && state.pendingIndicatorEl.parentNode) {
    state.pendingIndicatorEl.parentNode.removeChild(state.pendingIndicatorEl);
  }
  state.pendingIndicatorEl = null;
}

export function addAgentErrorMessage(text) {
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
