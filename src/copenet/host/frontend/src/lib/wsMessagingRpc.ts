import type { MessageDestination, MessagingConfig, TelegramSessionRoute } from '../types/backend';
import {
  normalizeDestination,
  normalizeMessagingConfig,
  normalizeTelegramRoute,
} from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function getMessagingConfigRpc(request: WsRpcRequest): Promise<MessagingConfig | null> {
  const payload = await request<{ config?: unknown | null }>('messaging.config.get', {});
  return normalizeMessagingConfig(payload.config);
}

export async function listMessagingDestinationsRpc(request: WsRpcRequest): Promise<MessageDestination[]> {
  const payload = await request<{ destinations?: unknown[] }>('messaging.destinations.list', {});
  return Array.isArray(payload.destinations)
    ? payload.destinations.map(normalizeDestination).filter((item): item is MessageDestination => item != null)
    : [];
}

export async function listMessagingRoutesRpc(request: WsRpcRequest): Promise<TelegramSessionRoute[]> {
  const payload = await request<{ routes?: unknown[] }>('messaging.routes.list', {});
  return Array.isArray(payload.routes)
    ? payload.routes.map(normalizeTelegramRoute).filter((item): item is TelegramSessionRoute => item != null)
    : [];
}

export async function updateMessagingApprovalPolicyRpc(
  request: WsRpcRequest,
  params: {
    requireApprovalByDefault: boolean;
    hardlineBlocklist?: string[];
  },
): Promise<MessagingConfig | null> {
  const payload = await request<{ config?: unknown | null }>('messaging.config.update', {
    approvalPolicy: {
      requireApprovalByDefault: params.requireApprovalByDefault,
      hardlineBlocklist: params.hardlineBlocklist || [],
    },
  });
  return normalizeMessagingConfig(payload.config);
}

export async function updateTelegramRuntimeDefaultsRpc(
  request: WsRpcRequest,
  params: {
    provider: string;
    model: string;
    systemPromptId: string;
    taskPromptId: string;
  },
): Promise<MessagingConfig | null> {
  const payload = await request<{ config?: unknown | null }>('messaging.config.update', {
    telegramDefaults: {
      provider: params.provider || undefined,
      model: params.model || undefined,
      systemPromptId: params.systemPromptId || undefined,
      taskPromptId: params.taskPromptId || undefined,
    },
  });
  return normalizeMessagingConfig(payload.config);
}

export async function testMessagingPlatformRpc(
  request: WsRpcRequest,
  platform = 'telegram',
): Promise<{
  config: MessagingConfig | null;
  result: {
    ok: boolean;
    connectionStatus: 'connected' | 'disconnected' | 'error' | 'unconfigured';
    message: string;
    verifiedAt: string | null;
  };
}> {
  const payload = await request<{
    config?: unknown | null;
    result?: Record<string, unknown>;
  }>('messaging.test', { platform });
  return {
    config: normalizeMessagingConfig(payload.config),
    result: {
      ok: Boolean(payload.result?.ok),
      connectionStatus:
        payload.result?.connectionStatus === 'connected' ||
        payload.result?.connectionStatus === 'disconnected' ||
        payload.result?.connectionStatus === 'error' ||
        payload.result?.connectionStatus === 'unconfigured'
          ? payload.result.connectionStatus
          : 'unconfigured',
      message: payload.result?.message ? String(payload.result.message) : '',
      verifiedAt: payload.result?.verifiedAt ? String(payload.result.verifiedAt) : null,
    },
  };
}

export async function upsertMessagingDestinationRpc(
  request: WsRpcRequest,
  destination: {
    id?: string;
    platform: string;
    target: string;
    displayName: string;
    threadLabel?: string | null;
    isDefault: boolean;
    requiresApproval: boolean;
    status?: 'configured' | 'unconfigured' | 'error';
  },
): Promise<{ destination: MessageDestination | null; config: MessagingConfig | null }> {
  const payload = await request<{ destination?: unknown | null; config?: unknown | null }>(
    'messaging.destinations.upsert',
    { destination },
  );
  return {
    destination: normalizeDestination(payload.destination),
    config: normalizeMessagingConfig(payload.config),
  };
}

export async function deleteMessagingDestinationRpc(
  request: WsRpcRequest,
  destinationId: string,
): Promise<{ deleted: boolean; config: MessagingConfig | null }> {
  const payload = await request<{ deleted?: unknown; config?: unknown | null }>('messaging.destinations.delete', {
    destinationId,
  });
  return {
    deleted: Boolean(payload.deleted),
    config: normalizeMessagingConfig(payload.config),
  };
}

export async function upsertMessagingRouteRpc(
  request: WsRpcRequest,
  route: {
    id?: string;
    platform: string;
    chatId: string;
    threadId?: string | null;
    sessionKey: string;
    titleOverride?: string | null;
  },
): Promise<{ route: TelegramSessionRoute | null; routes: TelegramSessionRoute[] }> {
  const payload = await request<{ route?: unknown | null; routes?: unknown[] }>('messaging.routes.upsert', {
    route,
  });
  return {
    route: normalizeTelegramRoute(payload.route),
    routes: Array.isArray(payload.routes)
      ? payload.routes.map(normalizeTelegramRoute).filter((item): item is TelegramSessionRoute => item != null)
      : [],
  };
}

export async function deleteMessagingRouteRpc(
  request: WsRpcRequest,
  routeId: string,
): Promise<{ deleted: boolean; routes: TelegramSessionRoute[] }> {
  const payload = await request<{ deleted?: unknown; routes?: unknown[] }>('messaging.routes.delete', {
    routeId,
  });
  return {
    deleted: Boolean(payload.deleted),
    routes: Array.isArray(payload.routes)
      ? payload.routes.map(normalizeTelegramRoute).filter((item): item is TelegramSessionRoute => item != null)
      : [],
  };
}
