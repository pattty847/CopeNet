import { useEffect, useRef, useState, type CSSProperties, type PointerEvent } from 'react';
import { ArrowUp, ChevronRight, MessageSquare, Square, X } from 'lucide-react';
import { MessageBubble } from '../../../components/MessageBubble';
import { ApprovalRequestCard } from '../../../components/ApprovalRequestCard';
import { InspectorDrawer } from '../../../components/runtime/InspectorDrawer';
import { useAppStore } from '../../../store/useAppStore';
import { useChartConversation } from './useChartConversation';
import { ChartDrawingsPanel } from './ChartDrawingsPanel';
import type { ChartWorkspaceController } from './useChartWorkspace';
import type { ChartDetail } from './types';
import './chartAgent.css';

const DETAILS: ChartDetail[] = ['quick', 'balanced', 'deep'];
const DETAIL_COPY = { quick: 'Compact context · precise reads on demand', balanced: 'Recent candles, indicators and focused inspection', deep: 'Wider history and a larger evidence budget' };
function date(value: number | null) { return value == null ? '…' : new Date(value * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit', timeZone: 'UTC' }); }

export function ChartAgentPanel({ workspace, symbol, timeframe }: { workspace: ChartWorkspaceController; symbol: string; timeframe: string }) {
  const conversation = useChartConversation(workspace);
  const [tab, setTab] = useState<'chat' | 'drawings'>('chat');
  const [width, setWidth] = useState(() => {
    const stored = Number(localStorage.getItem('copenet.chart.panelWidth'));
    return stored >= 320 && stored <= 640 ? stored : 380;
  });
  const resizeStart = useRef<{ x: number; width: number } | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const approvals = useAppStore((state) => state.pendingApprovalsById);
  const inspect = useAppStore((state) => state.setInspectorTarget);
  const connection = useAppStore((state) => state.wsStatus);
  const pendingApproval = Object.values(approvals).find((approval) => approval.sessionKey === conversation.sessionKey && approval.status === 'pending');
  useEffect(() => { if (workspace.selectedObjectId) setTab('drawings'); }, [workspace.selectedObjectId]);
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }); }, [conversation.messages.length, conversation.activeRun]);
  const resize = (event: PointerEvent<HTMLDivElement>) => {
    if (!resizeStart.current) return;
    const next = Math.min(640, Math.max(320, resizeStart.current.width + resizeStart.current.x - event.clientX));
    setWidth(next); localStorage.setItem('copenet.chart.panelWidth', String(next));
  };
  const disabled = conversation.sending || Boolean(conversation.activeRun) || !workspace.document || connection !== 'connected' || Boolean(conversation.session?.archived);
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
      </div>
      {workspace.error && <div className="ca-error" role="alert">{workspace.error} <button onClick={workspace.retry}>Retry</button></div>}
      <div className="ca-scroll" role="tabpanel">
        {tab === 'drawings' ? <ChartDrawingsPanel workspace={workspace} /> : <>
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
      <form className="ca-composer" onSubmit={(event) => { event.preventDefault(); setTab('chat'); void conversation.send(); }}>
        <div className="ca-runtime">
          <label>Provider<select aria-label="Chart agent provider" value={conversation.provider} disabled={Boolean(conversation.sessionKey) || conversation.sending} onChange={(event) => conversation.changeProvider(event.target.value)}>
            {conversation.providers.map((provider) => <option key={provider.id} value={provider.id} disabled={!provider.available}>{provider.displayName}</option>)}
          </select></label>
          <label>Model<select aria-label="Chart agent model" value={conversation.model ?? ''} disabled={Boolean(conversation.activeRun) || conversation.sending} onChange={(event) => conversation.changeModel(event.target.value)}>
            <option value="">Provider default</option>{conversation.model && !conversation.models.some((model) => model.id === conversation.model) && <option value={conversation.model}>{conversation.model}</option>}
            {conversation.models.map((model) => <option key={model.id} value={model.id}>{model.displayName}</option>)}
          </select></label>
        </div>
        <div className="ca-detail"><label htmlFor="chart-detail">Detail <strong>{conversation.detail}</strong></label>
          <input id="chart-detail" type="range" min={0} max={2} step={1} value={DETAILS.indexOf(conversation.detail)} aria-valuetext={conversation.detail}
            onChange={(event) => conversation.setDetail(DETAILS[Number(event.target.value)])} />
          <small>{DETAIL_COPY[conversation.detail]}</small></div>
        <div className="ca-access"><label><input type="checkbox" checked={conversation.access === 'annotate'} onChange={(event) => conversation.setAccess(event.target.checked ? 'annotate' : 'read')} /> Allow chart annotations</label>
          <details><summary>Context settings</summary><label><input type="checkbox" checked={workspace.includeAccountContext} onChange={(event) => workspace.setIncludeAccountContext(event.target.checked)} /> Include new account context</label><small>Earlier conversation, drawings and profile context are retained.</small></details></div>
        {workspace.selection && <div className="ca-selection">Selected {date(workspace.selection.from)} — {date(workspace.selection.to)}<button type="button" aria-label="Clear chart selection" onClick={() => workspace.setSelection(null)}><X size={12} /></button></div>}
        <label className="ca-input-label" htmlFor="chart-question">Ask about this chart</label>
        <textarea id="chart-question" value={conversation.input} onChange={(event) => conversation.setInput(event.target.value)} placeholder="Ask about a pattern, level, or selected region…" rows={2}
          onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!disabled) { setTab('chat'); void conversation.send(); } } }} />
        {conversation.error && <div className="ca-error" role="alert">{conversation.error}<button type="button" onClick={conversation.resetSubmission}>Use current view for a new request</button></div>}
        <div className="ca-send-row"><span>{connection !== 'connected' ? 'Host disconnected' : conversation.session?.archived ? 'Session archived' : conversation.sending ? 'Capturing chart…' : 'Current view captured on send'}</span>
          {conversation.activeRun ? <button type="button" aria-label="Stop chart agent" onClick={() => void conversation.stop()}><Square size={14} /> Stop</button>
            : <button type="submit" aria-label="Send chart question" disabled={disabled || !conversation.input.trim()}><ArrowUp size={16} /></button>}
        </div>
      </form>
    </aside>
    {workspace.open && <InspectorDrawer />}
  </>;
}
