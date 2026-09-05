import { useEffect, useRef, useState } from 'react';
import { ArrowUp, PenLine, SlidersHorizontal, Square, X } from 'lucide-react';
import { useAppStore } from '../../../store/useAppStore';
import { ChartPopoverShell } from '../chartPopoverShell';
import type { useChartConversation } from './useChartConversation';
import type { ChartWorkspaceController } from './useChartWorkspace';
import type { ChartDetail } from './types';

const DETAIL_COPY = { quick: 'Compact context · precise reads on demand', balanced: 'Recent candles, indicators and focused inspection', deep: 'Wider history and a larger evidence budget' };
function date(value: number) { return new Date(value * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: '2-digit', timeZone: 'UTC' }); }

export function ChartAgentComposer({ conversation, workspace, onSend }: {
  conversation: ReturnType<typeof useChartConversation>;
  workspace: ChartWorkspaceController;
  onSend: () => void;
}) {
  const connection = useAppStore((state) => state.wsStatus);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const settingsAnchor = useRef<HTMLButtonElement>(null);
  const settingsBody = useRef<HTMLDivElement>(null);
  useEffect(() => { if (settingsOpen && workspace.open) settingsBody.current?.focus(); }, [settingsOpen, workspace.open]);
  const disabled = conversation.sending || Boolean(conversation.activeRun) || !workspace.document || connection !== 'connected' || Boolean(conversation.session?.archived);
  const providerName = conversation.providers.find((provider) => provider.id === conversation.provider)?.displayName ?? conversation.provider;
  const modelName = conversation.models.find((model) => model.id === conversation.model)?.displayName ?? conversation.model ?? 'Provider default';
  const closeSettings = () => {
    if (settingsBody.current?.closest('.tw-pop')?.contains(document.activeElement)) settingsAnchor.current?.focus();
    setSettingsOpen(false);
  };
  const status = connection !== 'connected' ? 'Host disconnected' : conversation.session?.archived ? 'Session archived' : conversation.sending ? 'Capturing chart…' : null;

  return <form className="ca-composer" onSubmit={(event) => { event.preventDefault(); if (!disabled) onSend(); }}>
    <div className="ca-controls">
      <select className="ca-model" aria-label="Chart agent model" title={`${providerName} · ${modelName}`} value={conversation.model ?? ''}
        disabled={Boolean(conversation.activeRun) || conversation.sending} onChange={(event) => conversation.changeModel(event.target.value)}>
        <option value="">Provider default</option>
        {conversation.model && !conversation.models.some((model) => model.id === conversation.model) && <option value={conversation.model}>{conversation.model}</option>}
        {conversation.models.map((model) => <option key={model.id} value={model.id}>{model.displayName}</option>)}
      </select>
      <select className="ca-detail-select" aria-label="Chart context detail" title={DETAIL_COPY[conversation.detail]} value={conversation.detail}
        onChange={(event) => conversation.setDetail(event.target.value as ChartDetail)}>
        <option value="quick">Quick</option><option value="balanced">Balanced</option><option value="deep">Deep</option>
      </select>
      <button type="button" className="ca-annotation-toggle" aria-label="Allow chart annotations" aria-pressed={conversation.access === 'annotate'}
        title={conversation.access === 'annotate' ? 'Chart annotations on' : 'Read only · chart annotations off'}
        onClick={() => conversation.setAccess(conversation.access === 'annotate' ? 'read' : 'annotate')}><PenLine size={15} /></button>
      <button type="button" ref={settingsAnchor} aria-label="Chart agent settings" aria-expanded={settingsOpen && workspace.open} aria-haspopup="dialog"
        title="Provider and context settings" data-account-context={workspace.includeAccountContext}
        onClick={() => setSettingsOpen(!settingsOpen)}><SlidersHorizontal size={15} />{workspace.includeAccountContext && <span className="ca-account-dot" aria-label="Account context included" />}</button>
    </div>
    <ChartPopoverShell anchor={settingsAnchor} open={settingsOpen && workspace.open} onClose={closeSettings} title="Chart agent settings" width={300}>
      <div className="ca-settings" ref={settingsBody} role="dialog" aria-label="Chart agent settings" tabIndex={-1}>
        <label>Provider<select aria-label="Chart agent provider" value={conversation.provider} disabled={Boolean(conversation.sessionKey) || conversation.sending}
          onChange={(event) => conversation.changeProvider(event.target.value)}>
          {conversation.providers.map((provider) => <option key={provider.id} value={provider.id} disabled={!provider.available}>{provider.displayName}</option>)}
        </select></label>
        {conversation.sessionKey && <small>Provider is fixed for this conversation. Start a new chat to change it.</small>}
        <p><strong>{conversation.detail} detail</strong><br />{DETAIL_COPY[conversation.detail]}</p>
        <label className="ca-setting-check"><input type="checkbox" checked={workspace.includeAccountContext} onChange={(event) => workspace.setIncludeAccountContext(event.target.checked)} />Include new account context</label>
        <small>Earlier conversation, drawings and profile context are retained.</small>
        <small>Current chart view is captured when you send.</small>
      </div>
    </ChartPopoverShell>
    {workspace.selection && <div className="ca-selection">Selected {date(workspace.selection.from)} — {date(workspace.selection.to)}<button type="button" aria-label="Clear chart selection" onClick={() => workspace.setSelection(null)}><X size={12} /></button></div>}
    <div className="ca-message-input">
      <label className="sr-only" htmlFor="chart-question">Ask about this chart</label>
      <textarea id="chart-question" value={conversation.input} onChange={(event) => conversation.setInput(event.target.value)} placeholder="Ask about this chart…" rows={2}
        onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!disabled) onSend(); } }} />
      {conversation.activeRun ? <button type="button" aria-label="Stop chart agent" title="Stop chart agent" onClick={() => void conversation.stop()}><Square size={15} /></button>
        : <button type="submit" aria-label="Send chart question" title="Send · current view captured" disabled={disabled || !conversation.input.trim()}><ArrowUp size={16} /></button>}
    </div>
    {status && <div className="ca-composer-status" role="status">{status}</div>}
    {conversation.error && <div className="ca-error" role="alert">{conversation.error}<button type="button" onClick={conversation.resetSubmission}>Use current view for a new request</button></div>}
  </form>;
}
