import type {
  Message,
  ObservabilityRunDetail,
  ObservabilitySettings,
  ObservabilityTraceEvent,
  PublicMessagePayload,
  SessionArtifactRecord,
  SessionRunRecord,
} from '../types/backend';
import { normalizeMessage } from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

function normalizeSettings(raw: unknown): ObservabilitySettings {
  const value = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {};
  const storage = value.traceStorage && typeof value.traceStorage === 'object'
    ? value.traceStorage as Record<string, unknown>
    : {};
  return {
    debugCapture: Boolean(value.debugCapture),
    captureScope: 'subsequent_runs',
    storage: 'local',
    lifecycleCapture: value.lifecycleCapture !== false,
    traceStorage: {
      fileCount: Number(storage.fileCount) || 0,
      totalBytes: Number(storage.totalBytes) || 0,
    },
  };
}

export async function getObservabilitySettingsRpc(request: WsRpcRequest): Promise<ObservabilitySettings> {
  const payload = await request<{ settings?: unknown }>('observability.settings.get', {});
  return normalizeSettings(payload.settings);
}

export async function updateObservabilitySettingsRpc(
  request: WsRpcRequest,
  debugCapture: boolean,
): Promise<ObservabilitySettings> {
  const payload = await request<{ settings?: unknown }>('observability.settings.update', { debugCapture });
  return normalizeSettings(payload.settings);
}

export async function purgeObservabilityTracesRpc(request: WsRpcRequest): Promise<ObservabilitySettings> {
  const payload = await request<{ settings?: unknown }>('observability.traces.purge', {});
  return normalizeSettings(payload.settings);
}

export async function getObservabilityRunRpc(
  request: WsRpcRequest,
  sessionKey: string,
  runId: string,
): Promise<ObservabilityRunDetail | null> {
  const payload = await request<{ detail?: Record<string, unknown> | null }>('observability.run.get', { sessionKey, runId });
  if (!payload.detail) return null;
  const rawMessages = Array.isArray(payload.detail.messages) ? payload.detail.messages as PublicMessagePayload[] : [];
  return {
    run: payload.detail.run as SessionRunRecord,
    messages: rawMessages.map((message, index) => normalizeMessage(
      message,
      sessionKey,
      `observability-${runId}-${index}`,
      (message.role as Message['role']) || 'assistant',
      (message.state as Message['state']) || 'final',
    )),
    events: Array.isArray(payload.detail.events) ? payload.detail.events as ObservabilityTraceEvent[] : [],
    artifacts: Array.isArray(payload.detail.artifacts) ? payload.detail.artifacts as SessionArtifactRecord[] : [],
    debugCaptured: Boolean(payload.detail.debugCaptured),
    lifecycleCaptured: Boolean(payload.detail.lifecycleCaptured),
  };
}
