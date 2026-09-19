import { useForecasts } from '../forecasts/useForecasts';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import type { ChartRenderStatus } from '../../../lib/wsMarketChart';
import { safeUUID } from '../../../lib/wsNormalizers';
import { useAppStore } from '../../../store/useAppStore';
import { ViewResources } from '../viewState/resources';
import { captureTickerView, instrumentFor } from '../viewState/capture';
import type { useTickerViewModel } from '../useTickerViewModel';
import type { ChartWorkspaceBridge, DrawingMode } from '../drawings/types';
import { DEFAULT_DRAWING_COLOR, DRAWING_KINDS } from '../drawings/kinds';
import { readChartStyle } from '../chartStyle/store';
import { loadMagnet, saveMagnet, type MagnetMode } from '../drawings/magnet';
import type { ChartDocument, ChartObject, ChartOperation, ChartSelection, ChartViewport, DrawingReceipt } from './types';

const EMPTY_VIEWPORT: ChartViewport = { from: null, to: null, logicalFrom: null, logicalTo: null };

export function useChartWorkspace(view: ReturnType<typeof useTickerViewModel>) {
  const connection = useAppStore((state) => state.wsStatus);
  const [viewId] = useState(safeUUID);
  const [resources] = useState(() => new ViewResources());
  const [open, setOpen] = useState(false);
  const [document, setDocument] = useState<ChartDocument | null>(null);
  const forecasts = useForecasts(document?.documentId, Boolean(document));
  const [selectedForecastId, setSelectedForecastId] = useState<string | null>(null);
  const [forecastVisibility, setForecastVisibility] = useState<Record<string, boolean>>({});
  const hiddenForecasts = useMemo(() => {
    const latest = forecasts.records.find((record) => record.status === 'published' && record.members.ta?.result?.kind === 'setup')?.forecastId;
    return new Set(forecasts.records.filter((record) => !(forecastVisibility[record.forecastId] ?? record.forecastId === latest)).map((record) => record.forecastId));
  }, [forecasts.records, forecastVisibility]);
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
      return receipt;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The drawing could not be saved.');
      await refresh().catch(() => undefined);
    } finally { setBusy(false); }
  }, [refresh]);

  // One tap deletes on a phone, so a delete stays reversible for a few seconds.
  const [deleted, setDeleted] = useState<{ label: string; batchId: string } | null>(null);
  useEffect(() => {
    if (!deleted) return;
    const timer = window.setTimeout(() => setDeleted(null), 6000);
    return () => window.clearTimeout(timer);
  }, [deleted]);
  const deleteObject = useCallback(async (id: string) => {
    const target = documentRef.current?.objects.find((object) => object.id === id);
    const receipt = await apply([{ kind: 'delete', objectId: id }]);
    if (documentRef.current?.objects.some((object) => object.id === id)) return;
    setSelectedObjectId(null);
    if (receipt && target) setDeleted({ label: target.label || DRAWING_KINDS[target.kind].label, batchId: receipt.batchId });
  }, [apply]);

  const [labelRequestId, setLabelRequestId] = useState<string | null>(null);
  const [magnet, setMagnetState] = useState<MagnetMode>(loadMagnet);
  const setMagnet = useCallback((next: MagnetMode) => { setMagnetState(next); saveMagnet(next); }, []);
  const [settingsObjectId, setSettingsObjectId] = useState<string | null>(null);
  const [draft, setDraft] = useState<ChartObject | null>(null);
  const openDrawingSettings = useCallback((id: string | null) => {
    if (id) setSelectedObjectId(id);
    setSettingsObjectId(id);
  }, []);

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
    timeframe: view.timeframe, bars: view.bars, enabled: !view.comparing, interactionEnabled: !busy, selectedObjectId, includeAccountContext, magnet, mode, selection,
    forecasts: { splitFingerprint: view.detail?.priceProvenance?.splitFingerprint, records: forecasts.records.filter((record) => record.documentId === document.documentId), hidden: hiddenForecasts, viewId,
      onSelect: setSelectedForecastId,
      onRendered: async (receipt) => { await wsClient.marketForecast.rendered(receipt); } },
    onViewport, onSelectRange: (range) => { setSelection(range); setMode('select'); }, onSelectObject: (id) => { setSelectedObjectId(id); },
    onDeleteObject: (id) => { void deleteObject(id); }, onOpenDrawingSettings: openDrawingSettings, settingsObjectId, draft, onDraft: setDraft,
    onCancelDrawing: () => { setMode('select'); },
    onCreate: (proposal) => {
      const id = safeUUID();
      void apply([{ kind: 'create', object: { ...proposal, id, label: DRAWING_KINDS[proposal.kind].label,
        color: DEFAULT_DRAWING_COLOR, visible: true, rationale: '', evidence: [],
        ...Object.fromEntries(Object.entries(readChartStyle().drawingDefaults[proposal.kind] ?? {}).filter(([, value]) => value !== undefined)) } }]);
      setSelectedObjectId(id); setMode('select');
      setLabelRequestId(DRAWING_KINDS[proposal.kind].form === 'point' ? id : null);
    },
    onUpdate: ({ id, patch }) => { void apply([{ kind: 'update', objectId: id, patch }]); },
    labelRequestId, deleted, onUndoDelete: () => { if (deleted) { void undo(deleted.batchId); setDeleted(null); } },
    onRendered,
  } : undefined;

  const capture = (accountContext = includeAccountContext) => {
    if (!document) throw new Error('Wait for the chart workspace to load.');
    return captureTickerView({ view, document, viewId, revision: ++captureRevision.current, viewport, selection,
      contributions: resources.read(view.viewSymbol), includeAccountContext: accountContext });
  };
  const toggleForecast = (id: string) => setForecastVisibility((previous) => ({ ...previous, [id]: hiddenForecasts.has(id) }));
  return { forecasts, selectedForecastId, setSelectedForecastId, hiddenForecasts, toggleForecast, resources, bridge, open, setOpen, document, sessionKey, setSessionKey, batches, renderStatus, viewId, mode, setMode, magnet, setMagnet,
    selectedObjectId, setSelectedObjectId, selection, setSelection, viewport, error, busy, apply, undo,
    includeAccountContext, setIncludeAccountContext, capture, refresh, retry: () => setRetryKey((key) => key + 1) };
}
export type ChartWorkspaceController = ReturnType<typeof useChartWorkspace>;
