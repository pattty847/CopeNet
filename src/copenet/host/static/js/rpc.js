/**
 * rpc.js — WebSocket RPC helpers.
 *
 * sendReq sends one request frame and resolves when the matching response arrives.
 * The WebSocket instance lives on state.ws and is managed by controllers/chat.js.
 */

import { state } from './state.js';

/**
 * Send one RPC request and return a Promise that resolves with the response payload.
 * @param {string} method
 * @param {object} params
 * @returns {Promise<object>}
 */
export function sendReq(method, params) {
  return new Promise((resolve, reject) => {
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
      reject(new Error('Not connected'));
      return;
    }
    const id = method + '-' + Math.random().toString(36).slice(2, 10);
    state.ws.send(JSON.stringify({ type: 'req', id, method, params }));

    const onMessage = (e) => {
      const frame = JSON.parse(e.data);
      if (frame.type === 'res' && frame.id === id) {
        state.ws.removeEventListener('message', onMessage);
        if (frame.ok) resolve(frame.payload || {});
        else reject(new Error((frame.error && frame.error.message) || 'RPC error'));
      }
    };
    state.ws.addEventListener('message', onMessage);
  });
}
