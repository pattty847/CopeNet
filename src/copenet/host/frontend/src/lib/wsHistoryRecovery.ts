import type { ChatEventPayload, PublicMessagePayload } from '../types/backend';

export interface ActiveHistoryRun {
  runId: string;
  seq: number;
  message: PublicMessagePayload;
}

type QueuedEvent = { payload: ChatEventPayload; apply: () => void };
const recovering = new Map<string, QueuedEvent[]>();
const recoveredSequences = new Map<string, Map<string, number>>();
const requests = new Map<string, Promise<void>>();

export function deferHistoryEvent(payload: ChatEventPayload, apply: () => void): boolean {
  const recoveredSeq = payload.runId ? recoveredSequences.get(payload.sessionKey)?.get(payload.runId) : undefined;
  if (recoveredSeq !== undefined && payload.seq <= recoveredSeq) return true;
  const queue = recovering.get(payload.sessionKey);
  if (!queue) return false;
  queue.push({ payload, apply });
  return true;
}

/** Serialize history replacement with live deltas, including reconnect races. */
export function recoverHistory(
  sessionKey: string,
  load: () => Promise<{ activeRun: ActiveHistoryRun | null; messages: PublicMessagePayload[] }>,
): Promise<void> {
  const existing = requests.get(sessionKey);
  if (existing) return existing;
  const queue: QueuedEvent[] = [];
  recovering.set(sessionKey, queue);
  const request = (async () => {
    let snapshot: Awaited<ReturnType<typeof load>> | undefined;
    try {
      snapshot = await load();
    } finally {
      recovering.delete(sessionKey);
      requests.delete(sessionKey);
      if (snapshot) {
        const sequences = new Map<string, number>();
        for (const message of snapshot.messages) {
          if (message.role === 'assistant' && message.runId) sequences.set(message.runId, Infinity);
        }
        if (snapshot.activeRun) sequences.set(snapshot.activeRun.runId, snapshot.activeRun.seq);
        recoveredSequences.set(sessionKey, sequences);
      }
      const completed = new Set(snapshot?.messages.filter((message) => message.role === 'assistant').map((message) => message.runId));
      for (const { payload, apply } of queue) {
        if (snapshot && completed.has(payload.runId)) continue;
        if (snapshot?.activeRun?.runId === payload.runId && payload.seq <= snapshot.activeRun.seq) continue;
        apply();
      }
    }
  })();
  requests.set(sessionKey, request);
  return request;
}
