import { MediaAsset, MediaAssetDetail } from '../types/backend';

const DEFAULT_DEV_TOKEN = 'dev-token';

function getHttpBaseUrl(): string {
  const envUrl = import.meta.env.VITE_COPNET_API_URL?.trim();
  if (envUrl) return envUrl.replace(/\/$/, '');
  return window.location.origin;
}

function getAuthToken(): string {
  const envToken = import.meta.env.VITE_COPNET_TOKEN?.trim() || '';
  const fromWindow = typeof window.COPNET_TOKEN === 'string' ? window.COPNET_TOKEN.trim() : '';
  const fromStorage = window.localStorage.getItem('copnet.token') || '';
  const fromMeta = document.querySelector('meta[name="copnet-token"]')?.getAttribute('content')?.trim() || '';
  return envToken || fromWindow || fromStorage || fromMeta || DEFAULT_DEV_TOKEN;
}

async function readJson<T>(response: Response): Promise<T> {
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok) {
    throw new Error(String((payload as { detail?: string; message?: string }).detail || (payload as { detail?: string; message?: string }).message || `Request failed (${response.status})`));
  }
  return payload as T;
}

function normalizeMediaAsset(raw: unknown): MediaAsset {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    assetId: String(payload.assetId || ''),
    appId: String(payload.appId || ''),
    sourceType: String(payload.sourceType || ''),
    sourceUrl: payload.sourceUrl ? String(payload.sourceUrl) : null,
    sourcePath: payload.sourcePath ? String(payload.sourcePath) : null,
    title: String(payload.title || 'Untitled asset'),
    mediaPath: payload.mediaPath ? String(payload.mediaPath) : null,
    transcriptPath: payload.transcriptPath ? String(payload.transcriptPath) : null,
    transcriptSource: payload.transcriptSource ? String(payload.transcriptSource) : null,
    transcriptExcerpt: String(payload.transcriptExcerpt || ''),
    metadata: (payload.metadata as Record<string, unknown> | undefined) || {},
    durationSeconds: typeof payload.durationSeconds === 'number' ? payload.durationSeconds : payload.durationSeconds ? Number(payload.durationSeconds) : null,
    latencyMs: typeof payload.latencyMs === 'number' ? payload.latencyMs : payload.latencyMs ? Number(payload.latencyMs) : null,
    createdAt: String(payload.createdAt || new Date().toISOString()),
    updatedAt: String(payload.updatedAt || new Date().toISOString()),
  };
}

function normalizeMediaAssetDetail(raw: unknown): MediaAssetDetail {
  const asset = normalizeMediaAsset(raw);
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    ...asset,
    transcriptContent: String(payload.transcriptContent || ''),
  };
}

export async function listMediaAssets(limit = 24): Promise<MediaAsset[]> {
  const response = await fetch(`${getHttpBaseUrl()}/api/v1/media/assets?limit=${limit}`, {
    headers: {
      Authorization: `Bearer ${getAuthToken()}`,
    },
  });
  const payload = await readJson<{ assets?: unknown[] }>(response);
  return Array.isArray(payload.assets) ? payload.assets.map(normalizeMediaAsset) : [];
}

export async function getMediaAssetDetail(assetId: string): Promise<MediaAssetDetail> {
  const response = await fetch(`${getHttpBaseUrl()}/api/v1/media/assets/${encodeURIComponent(assetId)}`, {
    headers: {
      Authorization: `Bearer ${getAuthToken()}`,
    },
  });
  const payload = await readJson<{ asset?: unknown }>(response);
  return normalizeMediaAssetDetail(payload.asset);
}

type ImportEvent =
  | { type: 'progress'; percent?: number; message?: string }
  | { type: 'chunk'; text?: string }
  | { type: 'done'; asset?: unknown }
  | { type: 'error'; message?: string };

export async function importMediaFromUrl(
  url: string,
  callbacks: {
    onProgress?: (message: string | null, percent: number | null) => void;
    onChunk?: (text: string) => void;
  } = {},
): Promise<MediaAsset> {
  const search = new URLSearchParams({ url });
  const response = await fetch(`${getHttpBaseUrl()}/api/v1/media/import/stream?${search.toString()}`, {
    headers: {
      Accept: 'text/event-stream',
      Authorization: `Bearer ${getAuthToken()}`,
    },
  });
  if (!response.ok || !response.body) {
    const payload = await readJson<{ detail?: string }>(response);
    throw new Error(String(payload.detail || 'Media import failed.'));
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finalAsset: MediaAsset | null = null;

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });

    let boundary = buffer.indexOf('\n\n');
    while (boundary >= 0) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const lines = block.split('\n');
      let eventName = 'message';
      let data = '';
      for (const line of lines) {
        if (line.startsWith('event:')) eventName = line.slice(6).trim();
        if (line.startsWith('data:')) data += line.slice(5).trim();
      }
      if (data) {
        const parsed = JSON.parse(data) as ImportEvent;
        if (eventName === 'progress' || parsed.type === 'progress') {
          if (parsed.type === 'progress') {
            callbacks.onProgress?.(parsed.message ?? null, typeof parsed.percent === 'number' ? parsed.percent : null);
          }
        } else if (eventName === 'chunk' || parsed.type === 'chunk') {
          if (parsed.type === 'chunk' && parsed.text) callbacks.onChunk?.(parsed.text);
        } else if (eventName === 'error' || parsed.type === 'error') {
          throw new Error(parsed.type === 'error' ? parsed.message || 'Media import failed.' : 'Media import failed.');
        } else if (eventName === 'done' || parsed.type === 'done') {
          if (parsed.type === 'done') {
            finalAsset = normalizeMediaAsset(parsed.asset);
          }
        }
      }
      boundary = buffer.indexOf('\n\n');
    }

    if (done) break;
  }

  if (!finalAsset) {
    throw new Error('Media import completed without an asset payload.');
  }
  return finalAsset;
}
