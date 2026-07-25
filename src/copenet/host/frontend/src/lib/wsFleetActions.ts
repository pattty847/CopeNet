import { useAppStore } from '../store/useAppStore';
import type { FleetRoom } from '../types/backend';
import {
  archiveFleetRoomRpc,
  createFleetRoomRpc,
  listFleetRoomsRpc,
  normalizeFleetEvent,
  sendFleetMessageRpc,
} from './wsFleetRpc';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export function handleFleetEventAction(payload: Record<string, unknown>) {
  const roomId = String(payload.roomId || '');
  const event = normalizeFleetEvent(payload.event);
  if (!roomId || !event.eventId) return;
  const store = useAppStore.getState();
  const existingRoom = store.fleetRooms.find((room) => room.roomId === roomId);
  if (existingRoom?.events.some((item) => item.eventId === event.eventId)) return;
  store.appendFleetEvent(roomId, event);
  if (event.kind === 'assistant' || event.kind === 'error') {
    store.settleFleetParticipant(roomId, event.author);
  }
}

export async function refreshFleetRoomsAction(request: WsRpcRequest, includeArchived = false): Promise<FleetRoom[]> {
  const rooms = await listFleetRoomsRpc(request, includeArchived);
  useAppStore.getState().setFleetRooms(rooms);
  return rooms;
}

export async function createFleetRoomAction(
  request: WsRpcRequest,
  title: string,
  workspaceRoot?: string | null,
): Promise<FleetRoom> {
  const room = await createFleetRoomRpc(request, { title, workspaceRoot });
  const store = useAppStore.getState();
  store.upsertFleetRoom(room);
  store.setActiveFleetRoomId(room.roomId);
  return room;
}

export async function sendFleetMessageAction(
  request: WsRpcRequest,
  roomId: string,
  target: string,
  message: string,
): Promise<void> {
  const participantIds = target.replace(/^@/, '') === 'everyone'
    ? ['chatgpt', 'claude']
    : [target.replace(/^@/, '')];
  const store = useAppStore.getState();
  store.enqueueFleetParticipants(roomId, participantIds);
  try {
    await sendFleetMessageRpc(request, roomId, target, message);
  } catch (error) {
    for (const participantId of participantIds) store.settleFleetParticipant(roomId, participantId);
    throw error;
  }
}

export async function archiveFleetRoomAction(request: WsRpcRequest, roomId: string): Promise<FleetRoom> {
  const room = await archiveFleetRoomRpc(request, roomId);
  useAppStore.getState().upsertFleetRoom(room);
  return room;
}
