import { ForecastRequestSheet } from '../forecasts/ForecastRequestSheet';
import { ForecastInspector } from '../forecasts/ForecastInspector';
import { ForecastList } from '../forecasts/ForecastList';
import { useViewResource } from '../viewState/resources';
import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from 'react';
import { ChevronRight, MessageSquare, X } from 'lucide-react';
import { MessageBubble } from '../../../components/MessageBubble';
import { ApprovalRequestCard } from '../../../components/ApprovalRequestCard';
import { InspectorDrawer } from '../../../components/runtime/InspectorDrawer';
import { useAppStore } from '../../../store/useAppStore';
import { useChartConversation } from './useChartConversation';
import { ChartDrawingsPanel } from './ChartDrawingsPanel';
import type { ChartWorkspaceController } from './useChartWorkspace';
import { ChartAgentComposer } from './ChartAgentComposer';
import './chartAgent.css';

function date(value: number | null) { return value == null ? '…' : new Date(value * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit', timeZone: 'UTC' }); }

export function ChartAgentPanel({ workspace, symbol, timeframe }: { workspace: ChartWorkspaceController; symbol: string; timeframe: string }) {
  const conversation = useChartConversation(workspace);
  const [tab, setTab] = useState<'chat' | 'drawings' | 'forecasts'>('chat');
  const [requestOpen, setRequestOpen] = useState(false);
  useViewResource(symbol, { key: 'panel:forecasts', kind: 'panel', label: 'Chart forecasts',
    status: workspace.forecasts.error ? 'stale' : workspace.forecasts.loading ? 'not-loaded' : workspace.forecasts.records.length ? 'loaded' : 'empty',
    rows: workspace.forecasts.records.filter((record) => record.documentId === workspace.document?.documentId).map((record) => ({ ...record, overlayVisible: !workspace.hiddenForecasts.has(record.forecastId) })),
    metadata: { source: 'forecast_store', accountContext: false, active: workspace.open && tab === 'forecasts', coverage: { loadedCount: workspace.forecasts.records.length, nextOffset: workspace.forecasts.nextOffset }, complete: workspace.forecasts.nextOffset == null, error: workspace.forecasts.error } });
  const [width, setWidth] = useState(() => {
    const stored = Number(localStorage.getItem('copenet.chart.panelWidth'));
    return stored >= 320 && stored <= 640 ? stored : 380;
  });
  const resizeStart = useRef<{ x: number; width: number } | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const approvals = useAppStore((state) => state.pendingApprovalsById);
  const inspect = useAppStore((state) => state.setInspectorTarget);
  const pendingApproval = Object.values(approvals).find((approval) => approval.sessionKey === conversation.sessionKey && approval.status === 'pending');
  useEffect(() => { if (workspace.selectedObjectId) setTab('drawings'); }, [workspace.selectedObjectId]);
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [conversation.messages.length, conversation.activeRun]);
  const resize = (event: PointerEvent<HTMLDivElement>) => {
    if (!resizeStart.current) return;
    const next = Math.min(640, Math.max(320, resizeStart.current.width + resizeStart.current.x - event.clientX));
    setWidth(next); localStorage.setItem('copenet.chart.panelWidth', String(next));
  };
  const captured = conversation.lastCapture;

  return <>
    <aside className="ca-panel" aria-label="Chart agent" hidden={!workspace.open} style={{ '--ca-width': `${width}px` } as CSSProperties}>
      <div className="ca-resizer" role="separator" aria-label="Resize chart agent" aria-orientation="vertical" tabIndex={0}
        aria-valuemin={320} aria-valuemax={640} aria-valuenow={width}
        onKeyDown={(event) => { if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); setWidth((current) => Math.min(640, Math.max(320, current + (event.key === 'ArrowLeft' ? 20 : -20)))); } }}
        onPointerDown={(event) => { resizeStart.current = { x: event.clientX, width }; event.currentTarget.setPointerCapture(event.pointerId); }}
        onPointerMove={resize} onPointerUp={() => { resizeStart.current = null; }} onPointerCancel={() => { resizeStart.current = null; }} />
      <header className="ca-header"><div><MessageSquare size={15} /><strong>Chart agent</strong><span className="ca-beta">Preview</span></div>
        <button type="button" onClick={() => void conversation.newConversation()} disabled={conversation.sending || Boolean(conversation.activeRun)} title="Start a separate chart conversation">New chat</button>
        <button aria-label="Close chart agent" onClick={() => workspace.setOpen(false)}><X size={16} /></button></header>
      <div className="ca-context"><strong>{symbol}</strong><span>{timeframe} candles</span><span>{date(workspace.viewport.from)} — {date(workspace.viewport.to)}</span></div>
      <div className="ca-tabs" role="tablist">
        <button role="tab" aria-selected={tab === 'chat'} onClick={() => setTab('chat')}>Conversation</button>
        <button role="tab" aria-selected={tab === 'drawings'} onClick={() => setTab('drawings')}>Drawings <span>{workspace.document?.objects.length ?? 0}</span></button>
        <button role="tab" aria-selected={tab === 'forecasts'} onClick={() => setTab('forecasts')}>Forecasts <span>{workspace.forecasts.records.length}</span></button>
      </div>
      {workspace.error && <div className="ca-error" role="alert">{workspace.error} <button onClick={workspace.retry}>Retry</button></div>}
      <div className="ca-scroll" role="tabpanel">
        {tab === 'forecasts' ? <>
          <p className="cf-empty">Latest setup shown. Use the eye controls to compare earlier overlays.</p>
          {workspace.forecasts.error && <p className="ca-error" role="alert">{workspace.forecasts.error}</p>}
          {workspace.forecasts.loading ? <p className="cf-empty" role="status">Loading forecasts…</p> : <ForecastList records={workspace.forecasts.records} hidden={workspace.hiddenForecasts} onToggle={workspace.toggleForecast} onSelect={workspace.setSelectedForecastId} />}
          {workspace.forecasts.nextOffset != null && <button type="button" className="tw-btn" onClick={workspace.forecasts.loadMore}>Load more forecasts</button>}
          <button type="button" className="tw-btn" style={{ margin: 12 }} onClick={() => setRequestOpen(true)} disabled={!workspace.document || conversation.sending || Boolean(conversation.activeRun)}>Forecast this chart</button>
        </> : tab === 'drawings' ? <ChartDrawingsPanel workspace={workspace} /> : <>
          {conversation.messages.length === 0 && <div className="ca-empty"><span className="ca-eyebrow">WORK WITH THE CHART</span>
            <h3>Ask. Inspect. Draw.</h3><p>Your current candles, indicators and research panels are captured when you send.</p>
            <button onClick={() => conversation.setInput('Inspect the visible range and draw the price levels you can justify. Explain the evidence for each one.')}>
              Mark the levels that matter <ChevronRight size={14} /></button>
            <button onClick={() => conversation.setInput('Explain what changed in the selected region. Read the exact candles and active indicator values.')}>
              Explain this region <ChevronRight size={14} /></button>
          </div>}
          <div className="ca-messages">{conversation.messages.map((message) => <div key={message.localId}>
            {message.role === 'user' && message.marketContext && <div className="ca-turn-context" title={message.marketContext.observationId}>
              <span>{message.marketContext.symbol ?? 'Captured chart'} {message.marketContext.timeframe ?? ''} · {message.marketContext.detail}</span>
              {message.runId && <button onClick={() => inspect({ kind: 'run', sessionKey: message.sessionKey, runId: message.runId! })}>Inspect context</button>}
            </div>}
            <MessageBubble message={message} />
          </div>)}</div>
          {pendingApproval && <ApprovalRequestCard approval={pendingApproval} />}
          {conversation.activeRun && <p className="ca-working" role="status">{pendingApproval ? 'Waiting for drawing approval…' : 'Working with your captured chart…'}</p>}
          {captured && <details className="ca-evidence"><summary>Captured context · {captured.capture.instrument.symbol} · {captured.capture.resources.length} sources</summary>
            <p>Observation {captured.observationId}<br />Captured view remains fixed for this turn.</p>
            {captured.capture.resources.map((resource) => <div key={resource.key}><span>{resource.label}</span><small>{resource.metadata.excluded ? 'excluded' : `${resource.rows.length} rows · ${resource.status}`}</small></div>)}
          </details>}
          <div ref={end} />
        </>}
      </div>
      <ChartAgentComposer onForecast={() => setRequestOpen(true)} conversation={conversation} workspace={workspace} onSend={() => { setTab('chat'); void conversation.send(); }} />
    </aside>
    {workspace.open && <InspectorDrawer />}
    {requestOpen && <ForecastRequestSheet symbol={symbol} conversation={conversation} workspace={workspace} onClose={() => setRequestOpen(false)} />}
    {workspace.selectedForecastId && <ForecastInspector forecastId={workspace.selectedForecastId} onClose={() => workspace.setSelectedForecastId(null)} />}
  </>;
}
