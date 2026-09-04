import { useAppStore } from '../store/useAppStore';
import type { DraftSettings, Session } from '../types/backend';
import type { ChartDocument, ChartEvidence, ChartOperation, DrawingReceipt, InstrumentRef, MarketCapture } from '../sections/market/chartAgent/types';
import { normalizeSession } from './wsNormalizers';
import { sendMessageToSessionAction, type SendMessageToSessionOptions } from './wsChatActions';

type Request = <T extends Record<string, unknown>>(method: string, params: Record<string, unknown>) => Promise<T>;
export interface MarketWorkspace { workspaceId: string; sessionKey: string | null }
export interface ChartRenderStatus { viewId: string; revision: number; status: string; objectIds: string[]; reason?: string }
export interface ChartDocumentPayload { document: ChartDocument; batches?: DrawingReceipt[]; renderStatus?: ChartRenderStatus[] }

export function createMarketChartApi(request: Request) {
  const listeners = new Set<(documentId: string) => void>();
  return {
    receive(payload: Record<string, unknown>) {
      if (typeof payload.documentId === 'string') listeners.forEach((listener) => listener(payload.documentId as string));
    },
    subscribe(listener: (documentId: string) => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    workspace(instrument: InstrumentRef) {
      return request<{ workspace: MarketWorkspace; document: ChartDocument }>('market.chart.workspace.get', { workspaceId: 'primary', instrument });
    },
    linkSession(sessionKey: string | null) {
      return request('market.chart.workspace.update', { workspaceId: 'primary', sessionKey });
    },
    async createSession(key: string, settings: DraftSettings): Promise<Session> {
      const params = { key, title: 'Chart research', provider: settings.provider, model: settings.model || undefined,
        systemPromptId: settings.systemPromptId || undefined, taskPromptId: settings.taskPromptId || 'none',
        personaId: settings.personaId || undefined, personaFlavorId: settings.personaFlavorId || undefined,
        personaPrivacyTier: settings.personaPrivacyTier || undefined, workspaceRoot: settings.workspaceRoot || undefined };
      let session: Session;
      try {
        const payload = await request<{ session: unknown }>('sessions.create', params);
        session = normalizeSession(payload.session);
      } catch (reason) {
        // A lost creation response must resolve its original stable key. Never
        // manufacture another session or silently reconcile a different binding.
        const payload = await request<{ sessions: unknown[] }>('sessions.list', { includeArchived: true });
        const existing = payload.sessions.map(normalizeSession).find((row) => row.key === key);
        if (!existing) throw reason;
        const fields = ['provider', 'model', 'systemPromptId', 'taskPromptId', 'personaId', 'personaFlavorId', 'personaPrivacyTier', 'workspaceRoot'] as const;
        if (existing.archived || fields.some((field) => (existing[field] || null) !== (params[field] || null))) {
          throw new Error('The saved chart draft already belongs to different session settings. Start a new conversation.');
        }
        session = existing;
      }
      useAppStore.getState().upsertSession(session);
      return session;
    },
    capture(sessionKey: string, captureId: string, capture: MarketCapture) {
      return request<{ observationId: string; documentId: string; viewId: string }>('market.chart.capture', { sessionKey, captureId, capture });
    },
    read(sessionKey: string | null, reference: ChartEvidence, offset = 0, includeAccountContext = false, documentId?: string) {
      return request<{ rows: Record<string, unknown>[]; label: string; metadata: Record<string, unknown>; nextOffset: number | null; matchedCount: number; offset: number }>(
        'market.chart.read', { ...(sessionKey ? { sessionKey } : {}), documentId, ...reference, offset, limit: 50, includeAccountContext });
    },
    document(documentId: string) { return request<ChartDocumentPayload & Record<string, unknown>>('market.chart.document.get', { documentId }); },
    apply(documentId: string, expectedRevision: number, operationId: string, operations: ChartOperation[]) {
      return request<DrawingReceipt & Record<string, unknown>>('market.chart.apply', { documentId, expectedRevision, operationId, operations });
    },
    undo(documentId: string, expectedRevision: number, operationId: string, batchId: string) {
      return request<DrawingReceipt & Record<string, unknown>>('market.chart.undo', { documentId, expectedRevision, operationId, batchId });
    },
    rendered(receipt: { documentId: string; revision: number; viewId: string; status: string; objectIds: string[]; reason?: string }) {
      return request('market.chart.rendered', receipt);
    },
    send(options: SendMessageToSessionOptions) { return sendMessageToSessionAction(request, options); },
  };
}
