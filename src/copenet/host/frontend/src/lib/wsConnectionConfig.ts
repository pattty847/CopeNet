const DEFAULT_DEV_TOKEN = 'dev-token';

/** The one place this key is spelled out for new code. `lib/appApi.ts`, `lib/useVoiceToText.ts`,
 *  and `workflows/meme/memeClient.ts` each still read `localStorage` for it under their own
 *  local copy of the string — pre-existing duplication this constant doesn't yet clean up. */
export const TOKEN_STORAGE_KEY = 'copnet.token';

function getEnvString(name: 'VITE_COPNET_WS_URL' | 'VITE_COPNET_TOKEN'): string {
  const meta = typeof import.meta !== 'undefined' ? (import.meta as ImportMeta & { env?: Record<string, unknown> }) : undefined;
  const value = meta?.env?.[name];
  return typeof value === 'string' ? value.trim() : '';
}

export function getWsUrl(): string {
  const envUrl = getEnvString('VITE_COPNET_WS_URL');
  if (envUrl) return envUrl;
  if (typeof window === 'undefined') return 'ws://127.0.0.1:17123/ws';
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${protocol}//${window.location.host}/ws`;
}

export function getAuthToken(): string {
  const envToken = getEnvString('VITE_COPNET_TOKEN');
  const fromWindow = typeof window !== 'undefined' && typeof window.COPNET_TOKEN === 'string' ? window.COPNET_TOKEN.trim() : '';
  const fromStorage = typeof window !== 'undefined' ? window.localStorage.getItem(TOKEN_STORAGE_KEY) || '' : '';
  const fromMeta =
    typeof document !== 'undefined' ? document.querySelector('meta[name="copnet-token"]')?.getAttribute('content')?.trim() || '' : '';
  return envToken || fromWindow || fromStorage || fromMeta || DEFAULT_DEV_TOKEN;
}
