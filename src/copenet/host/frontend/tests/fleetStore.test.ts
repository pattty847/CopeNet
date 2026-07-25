import assert from 'node:assert/strict';
import test from 'node:test';

import { handleFleetEventAction, sendFleetMessageAction } from '../src/lib/wsFleetActions';
import { useAppStore } from '../src/store/useAppStore';
import type { FleetRoom } from '../src/types/backend';

function room(): FleetRoom {
  return {
    roomId: 'fleet-one',
    title: 'Research',
    status: 'active',
    mode: 'manual',
    participants: {
      chatgpt: { participantId: 'chatgpt', provider: 'openai-codex', model: 'gpt-test', laneSessionKey: 'lane-gpt' },
      claude: { participantId: 'claude', provider: 'claude-cli', model: 'claude-test', laneSessionKey: 'lane-claude' },
    },
    deliveryCursors: { chatgpt: 0, claude: 0 },
    events: [],
    createdAt: '2026-07-17T00:00:00Z',
    updatedAt: '2026-07-17T00:00:00Z',
  };
}

test('Fleet event delivery deduplicates events and settles only its participant', () => {
  useAppStore.setState({
    fleetRooms: [room()],
    activeFleetRoomId: 'fleet-one',
    fleetPendingCountsByRoom: { 'fleet-one': { chatgpt: 1, claude: 1 } },
  });
  const payload = {
    roomId: 'fleet-one',
    event: {
      eventId: 'event-one',
      seq: 2,
      kind: 'assistant',
      author: 'chatgpt',
      content: 'Independent answer',
      metadata: {},
      createdAt: '2026-07-17T00:01:00Z',
    },
  };

  handleFleetEventAction(payload);
  handleFleetEventAction(payload);

  const state = useAppStore.getState();
  assert.equal(state.fleetRooms[0].events.length, 1);
  assert.deepEqual(state.fleetPendingCountsByRoom['fleet-one'], { chatgpt: 0, claude: 1 });
});

test('queued everyone sends use independent per-participant counts', async () => {
  useAppStore.setState({ fleetPendingCountsByRoom: {} });
  const requests: Array<{ method: string; params: Record<string, unknown> }> = [];
  const request = async (method: string, params: Record<string, unknown>) => {
    requests.push({ method, params });
    return {};
  };

  await sendFleetMessageAction(request as never, 'fleet-one', '@everyone', 'First');
  await sendFleetMessageAction(request as never, 'fleet-one', '@everyone', 'Second');

  assert.equal(requests.length, 2);
  assert.deepEqual(useAppStore.getState().fleetPendingCountsByRoom['fleet-one'], { chatgpt: 2, claude: 2 });
});
