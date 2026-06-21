import type { RuntimeContext } from '../types/backend';
import { normalizeRuntimeContext } from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function browseWorkspaceRootRpc(
  request: WsRpcRequest,
): Promise<{ workspaceRoot: string | null; runtimeContext: RuntimeContext | null }> {
  const payload = await request<{ workspaceRoot?: string | null; runtimeContext?: unknown | null }>('runtime.workspace.browse', {});
  return {
    workspaceRoot: payload.workspaceRoot ? String(payload.workspaceRoot) : null,
    runtimeContext: normalizeRuntimeContext(payload.runtimeContext),
  };
}

export async function setWorkspaceRootRpc(request: WsRpcRequest, workspaceRoot: string): Promise<RuntimeContext> {
  const payload = await request<{ workspaceRoot?: string | null; runtimeContext?: unknown | null }>('runtime.workspace.set', {
    workspaceRoot,
  });
  const runtimeContext = normalizeRuntimeContext(payload.runtimeContext);
  if (!runtimeContext) {
    throw new Error('Workspace root update returned no runtime context.');
  }
  return runtimeContext;
}
