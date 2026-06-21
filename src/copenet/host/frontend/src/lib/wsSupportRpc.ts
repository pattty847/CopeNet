import type {
  ApodResult,
  PromptOptimizationResult,
  PromptOptimizationVariant,
  ProviderAuthStatus,
  PulseRecord,
  Session,
  SessionMergeState,
  ShellAllowlistEntry,
  WorkspaceFile,
  WorkspaceFileContent,
} from '../types/backend';
import {
  normalizeMergeState,
  normalizePulse,
  normalizeSession,
  normalizeShellAllowlist,
} from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function fetchApodRpc(request: WsRpcRequest, opts?: { date?: string; refresh?: boolean }): Promise<ApodResult> {
  const payload = await request<Partial<ApodResult>>('nasa.apod', {
    date: opts?.date,
    refresh: opts?.refresh ?? false,
  });
  return {
    configured: Boolean(payload.configured),
    apod: payload.apod ?? null,
    error: payload.error ?? null,
  };
}

export async function listPulsesRpc(request: WsRpcRequest): Promise<PulseRecord[]> {
  const payload = await request<{ pulses?: unknown[] }>('pulse.list', {});
  return Array.isArray(payload.pulses)
    ? payload.pulses.map(normalizePulse).filter((item): item is PulseRecord => item != null)
    : [];
}

export async function createPulseFromSessionRpc(
  request: WsRpcRequest,
  params: {
    sessionKey: string;
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
  },
): Promise<PulseRecord> {
  const payload = await request<{ pulse: unknown }>('pulse.create_from_session', {
    sessionKey: params.sessionKey,
    provider: params.provider,
    model: params.model || undefined,
    systemPromptId: params.systemPromptId || undefined,
    taskPromptId: params.taskPromptId || undefined,
  });
  const pulse = normalizePulse(payload.pulse);
  if (!pulse) throw new Error('Pulse creation returned no pulse.');
  return pulse;
}

export async function dismissPulseRpc(request: WsRpcRequest, pulseId: string): Promise<PulseRecord> {
  const payload = await request<{ pulse: unknown }>('pulse.dismiss', { pulseId });
  const pulse = normalizePulse(payload.pulse);
  if (!pulse) throw new Error('Pulse dismiss returned no pulse.');
  return pulse;
}

export async function savePulsesRpc(
  request: WsRpcRequest,
  params: {
    pulseIds: string[];
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
    workspaceRoot: string;
  },
): Promise<{ session: Session; mergeState: SessionMergeState | null }> {
  const payload = await request<{ session: unknown; mergeState?: unknown | null }>('pulse.save', {
    pulseIds: params.pulseIds,
    provider: params.provider,
    model: params.model || undefined,
    systemPromptId: params.systemPromptId || undefined,
    taskPromptId: params.taskPromptId || undefined,
    workspaceRoot: params.workspaceRoot || undefined,
  });
  return {
    session: normalizeSession(payload.session),
    mergeState: normalizeMergeState(payload.mergeState),
  };
}

export async function listShellAllowlistRpc(request: WsRpcRequest): Promise<ShellAllowlistEntry[]> {
  const payload = await request<{ commands?: unknown[] }>('permissions.allowlist.list', {});
  return normalizeShellAllowlist(payload.commands);
}

export async function addShellAllowlistRpc(request: WsRpcRequest, command: string): Promise<ShellAllowlistEntry[]> {
  const payload = await request<{ commands?: unknown[] }>('permissions.allowlist.add', { command });
  return normalizeShellAllowlist(payload.commands);
}

export async function removeShellAllowlistRpc(request: WsRpcRequest, command: string): Promise<ShellAllowlistEntry[]> {
  const payload = await request<{ commands?: unknown[] }>('permissions.allowlist.remove', { command });
  return normalizeShellAllowlist(payload.commands);
}

export async function listWorkspaceFilesRpc(request: WsRpcRequest, key: string): Promise<{ root: string; files: WorkspaceFile[] }> {
  return request<{ root: string; files: WorkspaceFile[] }>('workspace.listFiles', { key });
}

export async function readWorkspaceFileRpc(request: WsRpcRequest, key: string, path: string): Promise<WorkspaceFileContent> {
  return request<WorkspaceFileContent & Record<string, unknown>>('workspace.readFile', { key, path });
}

export async function writeWorkspaceFileRpc(
  request: WsRpcRequest,
  key: string,
  path: string,
  content: string,
): Promise<WorkspaceFileContent & { digest: string; revertible: boolean }> {
  return request<WorkspaceFileContent & { digest: string; revertible: boolean } & Record<string, unknown>>(
    'workspace.writeFile',
    { key, path, content },
  );
}

export async function readPersonaFileRpc(request: WsRpcRequest, path: string): Promise<WorkspaceFileContent> {
  return request<WorkspaceFileContent & Record<string, unknown>>('persona.readFile', { path });
}

export async function writePersonaFileRpc(
  request: WsRpcRequest,
  path: string,
  content: string,
): Promise<WorkspaceFileContent & { digest: string; revertible: boolean }> {
  return request<WorkspaceFileContent & { digest: string; revertible: boolean } & Record<string, unknown>>(
    'persona.writeFile',
    { path, content },
  );
}

export async function optimizePromptRpc(
  request: WsRpcRequest,
  options: {
    prompt: string;
    provider?: string;
    model?: string;
    customTransform?: string;
  },
): Promise<PromptOptimizationResult> {
  const payload = await request<{
    variants?: PromptOptimizationVariant[];
    provider?: string;
    model?: string | null;
  }>('prompts.optimize', {
    prompt: options.prompt,
    provider: options.provider || undefined,
    model: options.model || undefined,
    customTransform: options.customTransform || undefined,
  });
  return {
    variants: Array.isArray(payload.variants)
      ? payload.variants
          .map((variant) => ({
            id: String(variant.id || ''),
            label: String(variant.label || ''),
            prompt: String(variant.prompt || ''),
            rationale: String(variant.rationale || ''),
          }))
          .filter((variant) => variant.id && variant.prompt)
      : [],
    provider: String(payload.provider || options.provider || ''),
    model: payload.model == null ? null : String(payload.model),
  };
}

export async function providerAuthStatusRpc(request: WsRpcRequest, providerId: string): Promise<ProviderAuthStatus> {
  const payload = await request<{ status: ProviderAuthStatus }>('providerAuth.status', { provider: providerId });
  return payload.status;
}

export async function providerAuthBeginLoginRpc(
  request: WsRpcRequest,
  providerId: string,
  redirectUri?: string,
): Promise<{ loginId: string; authorizeUrl: string; redirectUri: string; state: string }> {
  const payload = await request<{ login: { loginId: string; authorizeUrl: string; redirectUri: string; state: string } }>(
    'providerAuth.beginLogin',
    { provider: providerId, redirectUri: redirectUri ?? undefined },
  );
  return payload.login;
}

export async function providerAuthLogoutRpc(request: WsRpcRequest, providerId: string): Promise<ProviderAuthStatus> {
  const payload = await request<{ status: ProviderAuthStatus }>('providerAuth.logout', { provider: providerId });
  return payload.status;
}
