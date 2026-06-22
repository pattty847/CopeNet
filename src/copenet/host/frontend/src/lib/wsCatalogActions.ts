import { useAppStore } from '../store/useAppStore';
import type { Model } from '../types/backend';
import { ensureDraftDefaultsAction } from './wsSessionActions';
import { normalizeModel } from './wsNormalizers';

type WsRpcRequest = <T extends Record<string, unknown>>(
  method: string,
  params: Record<string, unknown>,
) => Promise<T>;

export async function loadModelsAction(
  request: WsRpcRequest,
  modelLoads: Map<string, Promise<Model[]>>,
  providerId: string,
): Promise<Model[]> {
  const store = useAppStore.getState();
  if (store.loadedModelProviders[providerId]) {
    return store.modelsByProvider[providerId] || [];
  }

  const inFlight = modelLoads.get(providerId);
  if (inFlight) return inFlight;

  const promise = request<{ models: unknown[] }>('models.list', { provider: providerId, kind: 'chat' })
    .then((payload) => {
      const models = (payload.models || []).map(normalizeModel);
      useAppStore.getState().setModelsForProvider(providerId, models);
      ensureDraftDefaultsAction();
      modelLoads.delete(providerId);
      return models;
    })
    .catch((error) => {
      useAppStore.getState().setModelsForProvider(providerId, []);
      modelLoads.delete(providerId);
      throw error;
    });

  modelLoads.set(providerId, promise);
  return promise;
}
