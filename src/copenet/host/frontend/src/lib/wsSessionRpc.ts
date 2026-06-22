import type {
  PublicMessagePayload,
  Session,
  SessionArtifactRecord,
  SessionExportPayload,
  SessionMergeState,
  SessionRunRecord,
  SessionStateRecord,
} from '../types/backend';
import { normalizeMergeState, normalizeSession } from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function createMergedSessionRpc(
  request: WsRpcRequest,
  params: {
    sourceSessionKeys: string[];
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
    workspaceRoot: string;
    title?: string;
  },
): Promise<{ session: Session; mergeState: SessionMergeState | null }> {
  const payload = await request<{ session: unknown; mergeState?: unknown | null }>('sessions.merge.create', {
    sourceSessionKeys: params.sourceSessionKeys,
    provider: params.provider,
    model: params.model || undefined,
    systemPromptId: params.systemPromptId || undefined,
    taskPromptId: params.taskPromptId || undefined,
    workspaceRoot: params.workspaceRoot || undefined,
    title: params.title || undefined,
  });
  return {
    session: normalizeSession(payload.session),
    mergeState: normalizeMergeState(payload.mergeState),
  };
}

export async function exportSessionRpc(request: WsRpcRequest, key: string): Promise<SessionExportPayload> {
  const payload = await request<{
    session: unknown;
    messages: PublicMessagePayload[];
    markdown: string;
  }>('sessions.export', { key });
  return {
    session: normalizeSession(payload.session),
    messages: (payload.messages || []).map((message) => message),
    markdown: String(payload.markdown || ''),
  };
}

export async function listSessionRunsRpc(request: WsRpcRequest, key: string, limit = 20): Promise<SessionRunRecord[]> {
  const payload = await request<{ runs?: SessionRunRecord[] }>('sessions.runs', { key, limit });
  return Array.isArray(payload.runs) ? payload.runs : [];
}

export async function listSessionArtifactsRpc(
  request: WsRpcRequest,
  key: string,
  limit = 50,
): Promise<SessionArtifactRecord[]> {
  const payload = await request<{ artifacts?: SessionArtifactRecord[] }>('sessions.artifacts', { key, limit });
  return Array.isArray(payload.artifacts) ? payload.artifacts : [];
}

export async function revertEditRpc(
  request: WsRpcRequest,
  key: string,
  path: string,
  afterDigest: string,
): Promise<{ ok: boolean; error?: string; path?: string; newDigest?: string }> {
  return request<{ ok: boolean; error?: string; path?: string; newDigest?: string }>(
    'sessions.revertEdit',
    { key, path, afterDigest },
  );
}

export async function resolveSessionRunRpc(
  request: WsRpcRequest,
  key: string,
  runId: string,
): Promise<SessionRunRecord | null> {
  const payload = await request<{ run?: SessionRunRecord | null }>('sessions.run', { key, runId });
  return payload.run ?? null;
}

export async function resolveSessionStateRpc(request: WsRpcRequest, key: string): Promise<SessionStateRecord | null> {
  const payload = await request<{ state?: SessionStateRecord | null }>('sessions.state', { key });
  return payload.state ?? null;
}

export async function resolveMergeStateRpc(request: WsRpcRequest, key: string): Promise<SessionMergeState | null> {
  const payload = await request<{ mergeState?: unknown | null }>('sessions.merge.state', { key });
  return normalizeMergeState(payload.mergeState);
}
