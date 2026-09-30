import type { DeskSnapshot, FocusState } from '../types/backend';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

function numberSeries(value: unknown): number[] {
  return Array.isArray(value) ? value.map((entry) => Number(entry) || 0) : [];
}

/** `avgLatencyMs` is null when nothing completed in the window. Coercing that to 0 would
 *  render "0 ms" and read as an impossibly fast desk rather than an idle one. */
function optionalNumber(value: unknown): number | null {
  return value == null ? null : Number(value);
}

function normalizeSnapshot(raw: unknown): DeskSnapshot {
  const value = asRecord(raw);
  const health = asRecord(value.health);
  const activity = Array.isArray(value.activity) ? value.activity : [];
  const quote = value.quote ? asRecord(value.quote) : null;
  return {
    generatedAt: String(value.generatedAt || ''),
    activity: activity.map((entry) => {
      const row = asRecord(entry);
      return {
        runId: String(row.runId || ''),
        sessionKey: String(row.sessionKey || ''),
        sessionTitle: String(row.sessionTitle || ''),
        provider: String(row.provider || ''),
        model: row.model == null ? null : String(row.model),
        status: String(row.status || ''),
        summary: String(row.summary || ''),
        toolCount: Number(row.toolCount) || 0,
        startedAt: String(row.startedAt || ''),
        completedAt: row.completedAt == null ? null : String(row.completedAt),
        durationMs: optionalNumber(row.durationMs),
        errored: Boolean(row.errored),
      };
    }),
    health: {
      activeSessions: Number(health.activeSessions) || 0,
      totalSessions: Number(health.totalSessions) || 0,
      inFlight: Number(health.inFlight) || 0,
      toolCalls: Number(health.toolCalls) || 0,
      errorRate: Number(health.errorRate) || 0,
      avgLatencyMs: optionalNumber(health.avgLatencyMs),
      runs: Number(health.runs) || 0,
      toolCallSeries: numberSeries(health.toolCallSeries),
      runSeries: numberSeries(health.runSeries),
      errorSeries: numberSeries(health.errorSeries),
      windowMinutes: Number(health.windowMinutes) || 60,
    },
    quote: quote ? { text: String(quote.text || ''), attribution: String(quote.attribution || '') } : null,
  };
}

function normalizeFocus(raw: unknown): FocusState {
  const value = asRecord(raw);
  const items = Array.isArray(value.items) ? value.items : [];
  return {
    items: items.map((entry) => {
      const row = asRecord(entry);
      return {
        itemId: String(row.itemId || ''),
        text: String(row.text || ''),
        done: Boolean(row.done),
        createdAt: String(row.createdAt || ''),
      };
    }),
    notes: String(value.notes || ''),
    quickLaunch: Array.isArray(value.quickLaunch) ? value.quickLaunch.map(String) : [],
    updatedAt: String(value.updatedAt || ''),
  };
}

export async function homeSnapshotRpc(request: WsRpcRequest, activityLimit = 8): Promise<DeskSnapshot> {
  const payload = await request<{ snapshot?: unknown }>('home.snapshot', { activityLimit });
  return normalizeSnapshot(payload.snapshot);
}

export async function homeFocusGetRpc(request: WsRpcRequest): Promise<FocusState> {
  const payload = await request<{ focus?: unknown }>('home.focus.get', {});
  return normalizeFocus(payload.focus);
}

/** Every mutation rewrites the whole small document and returns it, so callers replace
 *  state rather than patching it — there is no partial-update shape to get wrong. */
export type FocusUpdate =
  | { op: 'add'; text: string }
  | { op: 'toggle'; itemId: string; done: boolean }
  | { op: 'rename'; itemId: string; text: string }
  | { op: 'remove'; itemId: string }
  | { op: 'clearDone' }
  | { op: 'notes'; notes: string }
  | { op: 'quickLaunch'; tiles: string[] };

export async function homeFocusUpdateRpc(request: WsRpcRequest, update: FocusUpdate): Promise<FocusState> {
  const payload = await request<{ focus?: unknown }>('home.focus.update', { ...update });
  return normalizeFocus(payload.focus);
}
