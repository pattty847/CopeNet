import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import type { ChartRenderStatus } from '../../../lib/wsMarketChart';
import { safeUUID } from '../../../lib/wsNormalizers';
import { useAppStore } from '../../../store/useAppStore';
import { ViewResources } from '../viewState/resources';
import { captureTickerView, instrumentFor } from '../viewState/capture';
import type { useTickerViewModel } from '../useTickerViewModel';
import type { ChartWorkspaceBridge, DrawingMode } from '../drawings/types';
import type { ChartDocument, ChartOperation, ChartSelection, ChartViewport, DrawingReceipt } from './types';

const EMPTY_VIEWPORT: ChartViewport = { from: null, to: null, logicalFrom: null, logicalTo: null };

export function useChartWorkspace(view: ReturnType<typeof useTickerViewModel>) {
  const connection = useAppStore((state) => state.wsStatus);
  const [viewId] = useState(safeUUID);
  const [resources] = useState(() => new ViewResources());
  const [open, setOpen] = useState(false);
  const [document, setDocument] = useState<ChartDocument | null>(null);
  const [sessionKey, updateSessionKey] = useState<string | null>(null);
  const sessionLinkRevision = useRef(0);
  const setSessionKey = useCallback((key: string | null) => {
    sessionLinkRevision.current += 1;
    updateSessionKey(key);
  }, []);
  const [batches, setBatches] = useState<DrawingReceipt[]>([]);
  const [renderStatus, setRenderStatus] = useState<ChartRenderStatus[]>([]);
  const [mode, setMode] = useState<DrawingMode>('select');
  const [selectedObjectId, setSelectedObjectId] = useState<string | null>(null);
  const [selection, setSelection] = useState<ChartSelection | null>(null);
  const [viewport, setViewport] = useState<ChartViewport>(EMPTY_VIEWPORT);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [includeAccountContext, setIncludeAccountContext] = useState(false);
  const [retryKey, setRetryKey] = useState(0);
  const documentRef = useRef(document);
  documentRef.current = document;
  const captureRevision = useRef(0);
  const instrument = useMemo(() => instrumentFor(view.viewSymbol), [view.viewSymbol]);

  useEffect(() => {
    let alive = true;
    const linkRevision = sessionLinkRevision.current;
    documentRef.current = null;
    setDocument(null); setViewport(EMPTY_VIEWPORT); setBatches([]); setRenderStatus([]); setSelectedObjectId(null); setSelection(null); setMode('select');
    if (connection !== 'connected') return;
    setError(null);
    wsClient.marketChart.workspace(instrument).then((payload) => {
      if (!alive) return;
      documentRef.current = payload.document;
      setDocument(payload.document);
      if (sessionLinkRevision.current === linkRevision) updateSessionKey(payload.workspace.sessionKey);
    }).catch((reason) => { if (alive) setError(reason instanceof Error ? reason.message : 'Chart workspace unavailable.'); });
    return () => { alive = false; };
  }, [instrument, connection, retryKey]);

  useEffect(() => { setSelection(null); setMode('select'); }, [view.timeframe]);
  const refresh = useCallback(async () => {
    const current = documentRef.current;
    if (!current || connection !== 'connected') return;
    const payload = await wsClient.marketChart.document(current.documentId);
    const latest = documentRef.current;
    if (latest?.documentId !== current.documentId || payload.document.revision < latest.revision) return;
    if (payload.document.revision > latest.revision) {
      documentRef.current = payload.document;
      setDocument(payload.document);
    }
    setBatches(payload.batches ?? []);
    setRenderStatus(payload.renderStatus ?? []);
  }, [connection]);

  useEffect(() => {
    const off = wsClient.marketChart.subscribe((id) => {
      if (documentRef.current?.documentId === id) void refresh().catch(() => undefined);
    });
    // Reconcile after tool writes, other-view edits and lost broadcast frames.
    const timer = window.setInterval(() => {
      if (globalThis.document.visibilityState === 'visible') void refresh().catch(() => undefined);
    }, open ? 1500 : 5000);
    return () => { off(); window.clearInterval(timer); };
  }, [open, refresh]);

  const apply = useCallback(async (operations: ChartOperation[]) => {
    const current = documentRef.current;
    if (!current) return;
    setBusy(true); setError(null);
    try {
      const receipt = await wsClient.marketChart.apply(current.documentId, current.revision, safeUUID(), operations);
      if (documentRef.current?.documentId === current.documentId) {
        if (receipt.document && receipt.document.revision >= documentRef.current.revision) {
          documentRef.current = receipt.document;
          setDocument(receipt.document);
        }
        await refresh();
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The drawing could not be saved.');
      await refresh().catch(() => undefined);
    } finally { setBusy(false); }
  }, [refresh]);

  const undo = useCallback(async (batchId: string) => {
    const current = documentRef.current;
    if (!current) return;
    setBusy(true); setError(null);
    try {
      const receipt = await wsClient.marketChart.undo(current.documentId, current.revision, safeUUID(), batchId);
      if (documentRef.current?.documentId === current.documentId) {
        if (receipt.document && receipt.document.revision >= documentRef.current.revision) {
          documentRef.current = receipt.document;
          setDocument(receipt.document);
        }
        await refresh();
      }
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'The drawing batch could not be undone.'); }
    finally { setBusy(false); }
  }, [refresh]);

  const onViewport = useCallback((next: ChartViewport) => setViewport((previous) =>
    previous.from === next.from && previous.to === next.to && previous.logicalFrom === next.logicalFrom && previous.logicalTo === next.logicalTo ? previous : next), []);
  const onRendered = useCallback((receipt: Parameters<ChartWorkspaceBridge['onRendered']>[0]) => {
    void wsClient.marketChart.rendered({ ...receipt, viewId }).catch(() => undefined);
  }, [viewId]);

  const bridge: ChartWorkspaceBridge | undefined = document && document.instrument.symbol === view.viewSymbol ? {
    documentId: document.documentId, revision: document.revision, objects: document.objects,
    timeframe: view.timeframe, enabled: !view.comparing, interactionEnabled: !busy, selectedObjectId, mode, selection,
    onViewport, onSelectRange: setSelection, onSelectObject: (id) => { setSelectedObjectId(id); if (id) setOpen(true); },
    onCreate: (proposal) => {
      const id = safeUUID();
      void apply([{ kind: 'create', object: { ...proposal, id, label: proposal.kind === 'level' ? 'Price level' : proposal.kind === 'zone' ? 'Price zone' : proposal.kind === 'trendline' ? 'Trendline' : 'Note',
        color: '#fb9423', visible: true, rationale: '', evidence: [] } }]);
      setSelectedObjectId(id); setMode('select'); setOpen(true);
    },
    onUpdate: ({ id, anchors }) => { void apply([{ kind: 'update', objectId: id, patch: { anchors } }]); },
    onRendered,
  } : undefined;

  const capture = () => {
    if (!document) throw new Error('Wait for the chart workspace to load.');
    return captureTickerView({ view, document, viewId, revision: ++captureRevision.current, viewport, selection,
      contributions: resources.read(view.viewSymbol), includeAccountContext });
  };
  return { resources, bridge, open, setOpen, document, sessionKey, setSessionKey, batches, renderStatus, viewId, mode, setMode,
    selectedObjectId, setSelectedObjectId, selection, setSelection, viewport, error, busy, apply, undo,
    includeAccountContext, setIncludeAccountContext, capture, refresh, retry: () => setRetryKey((key) => key + 1) };
}
export type ChartWorkspaceController = ReturnType<typeof useChartWorkspace>;
