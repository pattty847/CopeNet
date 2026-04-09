/**
 * auth.js — websocket endpoint and browser-side token lookup.
 */

export const WS_URL = (location.protocol === "https:" ? "wss:" : "ws:") + "//" + location.host + "/ws";

const DEFAULT_DEV_TOKEN = "dev-token";

export function getAuthToken() {
  const fromWindow = typeof window.COPNET_TOKEN === "string" ? window.COPNET_TOKEN.trim() : "";
  const fromStorage = window.localStorage.getItem("copnet.token") || "";
  const fromMeta =
    document.querySelector('meta[name="copnet-token"]')?.getAttribute("content")?.trim() || "";
  return fromWindow || fromStorage || fromMeta || DEFAULT_DEV_TOKEN;
}
