import type { FleetParticipant, FleetRoom, FleetRoomEvent, FleetToolReceipt } from '../types/backend';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

function normalizeToolReceipt(raw: unknown): FleetToolReceipt {
  const payload = (raw || {}) as Record<string, unknown>;
  return {
    toolId: payload.toolId ? String(payload.toolId) : null,
    ok: payload.ok !== false,
    summary: payload.summary ? String(payload.summary) : null,
    preview: payload.preview ?? null,
  };
}

export function normalizeFleetEvent(raw: unknown): FleetRoomEvent {
  const payload = (raw || {}) as Record<string, unknown>;
  const metadata = (payload.metadata || {}) as Record<string, unknown>;
  return {
    eventId: String(payload.eventId || ''),
    seq: Number(payload.seq || 0),
    kind: ['operator', 'assistant', 'error'].includes(String(payload.kind))
      ? String(payload.kind) as FleetRoomEvent['kind']
      : 'error',
    author: String(payload.author || 'unknown'),
    content: String(payload.content || ''),
    metadata: {
      target: metadata.target ? String(metadata.target) : undefined,
      runId: metadata.runId ? String(metadata.runId) : null,
      toolReceipts: Array.isArray(metadata.toolReceipts)
        ? metadata.toolReceipts.map(normalizeToolReceipt)
        : undefined,
    },
    createdAt: String(payload.createdAt || new Date().toISOString()),
  };
}

export function normalizeFleetRoom(raw: unknown): FleetRoom {
  const payload = (raw || {}) as Record<string, unknown>;
  const rawParticipants = (payload.participants || {}) as Record<string, unknown>;
  const participants = Object.fromEntries(Object.entries(rawParticipants).map(([participantId, value]) => {
    const participant = (value || {}) as Record<string, unknown>;
    return [participantId, {
      participantId: String(participant.participantId || participantId),
      provider: String(participant.provider || ''),
      model: participant.model ? String(participant.model) : null,
      laneSessionKey: String(participant.laneSessionKey || ''),
    } satisfies FleetParticipant];
  }));
  const rawCursors = (payload.deliveryCursors || {}) as Record<string, unknown>;
  return {
    roomId: String(payload.roomId || ''),
    title: String(payload.title || 'Fleet Room'),
    status: payload.status === 'archived' ? 'archived' : 'active',
    mode: 'manual',
    participants,
    deliveryCursors: Object.fromEntries(Object.entries(rawCursors).map(([key, value]) => [key, Number(value || 0)])),
    events: Array.isArray(payload.events) ? payload.events.map(normalizeFleetEvent) : [],
    createdAt: String(payload.createdAt || new Date().toISOString()),
    updatedAt: String(payload.updatedAt || new Date().toISOString()),
  };
}

export async function listFleetRoomsRpc(request: WsRpcRequest, includeArchived = false): Promise<FleetRoom[]> {
  const payload = await request<{ rooms?: unknown[] }>('fleet.list', { includeArchived });
  return Array.isArray(payload.rooms) ? payload.rooms.map(normalizeFleetRoom) : [];
}

export async function createFleetRoomRpc(
  request: WsRpcRequest,
  options: { title: string; workspaceRoot?: string | null },
): Promise<FleetRoom> {
  const payload = await request<{ room: unknown }>('fleet.create', {
    title: options.title,
    workspaceRoot: options.workspaceRoot || undefined,
  });
  return normalizeFleetRoom(payload.room);
}

export async function sendFleetMessageRpc(
  request: WsRpcRequest,
  roomId: string,
  target: string,
  message: string,
): Promise<void> {
  await request('fleet.send', { roomId, target, message });
}

export async function archiveFleetRoomRpc(request: WsRpcRequest, roomId: string): Promise<FleetRoom> {
  const payload = await request<{ room: unknown }>('fleet.archive', { roomId });
  return normalizeFleetRoom(payload.room);
}
