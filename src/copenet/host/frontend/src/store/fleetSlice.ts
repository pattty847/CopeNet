import type { StoreApi } from 'zustand';
import type { FleetRoom, FleetRoomEvent } from '../types/backend';

export type AgentsWorkspaceMode = 'chat' | 'fleet';

export interface FleetSlice {
  agentsWorkspaceMode: AgentsWorkspaceMode;
  fleetRooms: FleetRoom[];
  activeFleetRoomId: string | null;
  fleetPendingCountsByRoom: Record<string, Record<string, number>>;
  // "New" clicked while in Fleet mode: show the room-create screen even though
  // an active room exists (starting a new room archives the current one).
  fleetCreateOpen: boolean;
  setAgentsWorkspaceMode: (mode: AgentsWorkspaceMode) => void;
  setFleetCreateOpen: (open: boolean) => void;
  setFleetRooms: (rooms: FleetRoom[]) => void;
  upsertFleetRoom: (room: FleetRoom) => void;
  setActiveFleetRoomId: (roomId: string | null) => void;
  appendFleetEvent: (roomId: string, event: FleetRoomEvent) => void;
  enqueueFleetParticipants: (roomId: string, participantIds: string[]) => void;
  settleFleetParticipant: (roomId: string, participantId: string) => void;
}

function sortRooms(rooms: FleetRoom[]) {
  return [...rooms].sort((left, right) => right.updatedAt.localeCompare(left.updatedAt));
}

export function createFleetSlice<T extends FleetSlice>(set: StoreApi<T>['setState']): FleetSlice {
  return {
    agentsWorkspaceMode: 'chat',
    fleetRooms: [],
    activeFleetRoomId: null,
    fleetPendingCountsByRoom: {},
    fleetCreateOpen: false,
    setAgentsWorkspaceMode: (mode) => set({ agentsWorkspaceMode: mode } as Partial<T>),
    setFleetCreateOpen: (open) => set({ fleetCreateOpen: open } as Partial<T>),
    setFleetRooms: (rooms) =>
      set((state) => ({
        fleetRooms: sortRooms(rooms),
        activeFleetRoomId: state.activeFleetRoomId && rooms.some((room) => room.roomId === state.activeFleetRoomId)
          ? state.activeFleetRoomId
          : rooms.find((room) => room.status === 'active')?.roomId || rooms[0]?.roomId || null,
      } as Partial<T>)),
    upsertFleetRoom: (room) =>
      set((state) => ({
        fleetRooms: sortRooms([...state.fleetRooms.filter((item) => item.roomId !== room.roomId), room]),
        activeFleetRoomId: state.activeFleetRoomId || room.roomId,
      } as Partial<T>)),
    setActiveFleetRoomId: (roomId) => set({ activeFleetRoomId: roomId } as Partial<T>),
    appendFleetEvent: (roomId, event) =>
      set((state) => ({
        fleetRooms: sortRooms(state.fleetRooms.map((room) => room.roomId !== roomId ? room : {
          ...room,
          events: room.events.some((item) => item.eventId === event.eventId)
            ? room.events
            : [...room.events, event].sort((left, right) => left.seq - right.seq),
          updatedAt: event.createdAt,
        })),
      } as Partial<T>)),
    enqueueFleetParticipants: (roomId, participantIds) =>
      set((state) => {
        const current = state.fleetPendingCountsByRoom[roomId] || {};
        const next = { ...current };
        for (const participantId of participantIds) {
          next[participantId] = (next[participantId] || 0) + 1;
        }
        return {
          fleetPendingCountsByRoom: { ...state.fleetPendingCountsByRoom, [roomId]: next },
        } as Partial<T>;
      }),
    settleFleetParticipant: (roomId, participantId) =>
      set((state) => {
        const next = { ...(state.fleetPendingCountsByRoom[roomId] || {}) };
        next[participantId] = Math.max(0, (next[participantId] || 0) - 1);
        return {
          fleetPendingCountsByRoom: { ...state.fleetPendingCountsByRoom, [roomId]: next },
        } as Partial<T>;
      }),
  };
}
