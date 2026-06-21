import { useAppStore } from '../store/useAppStore';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function decideApprovalAction(
  request: WsRpcRequest,
  approvalId: string,
  decision: 'approved' | 'approved_always' | 'rejected',
  note?: string,
): Promise<{ ok: boolean; error?: string }> {
  return request<{ ok: boolean; error?: string }>('chat.decideApproval', { approvalId, decision, note });
}

export async function abortActiveRunAction(request: WsRpcRequest): Promise<void> {
  const store = useAppStore.getState();
  if (!store.activeRunId && !store.activeSessionKey) return;
  await request('chat.abort', {
    sessionKey: store.activeSessionKey || undefined,
    runId: store.activeRunId || undefined,
  });
}
