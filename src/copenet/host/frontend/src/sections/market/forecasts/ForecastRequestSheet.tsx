import { useEffect, useRef, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { safeUUID } from '../../../lib/wsNormalizers';
import { MonitoringSheet } from '../monitoring/MonitoringSheet';
import type { ScanDefinition, ScanPreview, ScansState } from '../monitoring/types';
import type { useChartConversation } from '../chartAgent/useChartConversation';
import type { ChartWorkspaceController } from '../chartAgent/useChartWorkspace';
import type { ForecastRequest } from './types';
import '../monitoring/monitoring.css';
import './forecasts.css';

export function focusedForecastScan(symbol: string): ScanDefinition {
  return { id: '', revision: 0, name: `Forecast · ${symbol}`, enabled: true, includeUniverse: false,
    symbols: [symbol], watchlists: [], excludeSymbols: [], sources: ['prices'], times: ['17:00'],
    days: [0, 1, 2, 3, 4], timezone: 'America/New_York', publishBrief: false, interpret: false };
}

export function ForecastRequestSheet({ symbol, conversation, workspace, onClose }: {
  symbol: string; conversation: ReturnType<typeof useChartConversation>; workspace: ChartWorkspaceController; onClose: () => void;
}) {
  const [paired, setPaired] = useState(false);
  const [expiry, setExpiry] = useState(10);
  const [tracking, setTracking] = useState('new');
  const trackingTouched = useRef(false);
  const [scans, setScans] = useState<ScansState | null>(null);
  const [preview, setPreview] = useState<ScanPreview | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [draft] = useState(() => focusedForecastScan(symbol));
  const pending = useRef<ForecastRequest | null>(null);
  useEffect(() => {
    let alive = true;
    wsClient.marketMonitoring.scans().then((next) => {
      if (!alive) return;
      setScans(next);
      const existing = next.scans.find((scan) => scan.enabled && !scan.includeUniverse && !scan.watchlists.length && !scan.interpret
        && !scan.publishBrief && scan.sources.length === 1 && scan.sources[0] === 'prices' && scan.resolvedSymbols.includes(symbol));
      if (existing && !trackingTouched.current) setTracking(existing.id);
    }).catch((reason) => { if (alive) setError(String(reason)); });
    return () => { alive = false; };
  }, [symbol]);
  const eligible = scans?.scans.filter((scan) => scan.enabled && !scan.includeUniverse && !scan.watchlists.length && !scan.interpret
    && !scan.publishBrief && scan.sources.length === 1 && scan.sources[0] === 'prices' && scan.resolvedSymbols.includes(symbol)) ?? [];
  const record = async () => {
    if (busy) return;
    setBusy(true); setError('');
    try {
      if (!conversation.model) throw new Error('Choose a specific model in the chart agent before recording a forecast.');
      if (tracking === 'new' && !preview) { setPreview(await wsClient.marketMonitoring.previewScan(draft)); return; }
      if (!pending.current) {
        const binding = await conversation.captureForForecast();
        pending.current = { ...binding, requestId: safeUUID(), provider: conversation.provider, model: conversation.model ?? '',
          detail: conversation.detail, paired, entryExpirySessions: expiry,
          ...(tracking === 'new' && preview ? { tracking: { scan: draft, scopeToken: preview.scopeToken } }
            : tracking !== 'paused' ? { trackingScanId: tracking } : {}) };
      }
      const result = await wsClient.marketForecast.request(pending.current);
      await workspace.forecasts.refresh();
      workspace.setSelectedForecastId(result.forecast.forecastId);
      onClose();
    } catch (reason) { setError(reason instanceof Error ? reason.message : 'Could not register the forecast. Retry preserves this request.'); }
    finally { setBusy(false); }
  };
  return <MonitoringSheet title={`Forecast ${symbol}`} onClose={onClose}>
    <form className="mm-monitor-form cf-request" onSubmit={(event) => { event.preventDefault(); void record(); }}>
      {!conversation.model && <p role="alert">Choose a specific model in the chart agent before recording a forecast.</p>}
      <p><strong>{conversation.model || 'Provider default'}</strong> · {conversation.detail} detail · current chart evidence</p>
      <p>{workspace.viewport.from != null && new Date(workspace.viewport.from * 1000).toLocaleDateString()} — {workspace.viewport.to != null && new Date(workspace.viewport.to * 1000).toLocaleDateString()}</p>
      <p>Record an entry, stop and profit targets for eight weeks. A valid setup is saved automatically; the model can also decline a setup.</p>
      <label>Entry expires after
        <select className="tw-input" value={expiry} disabled={busy || Boolean(pending.current)} onChange={(event) => setExpiry(Number(event.target.value))}>
          {[5, 10, 20].map((value) => <option value={value} key={value}>{value} exchange sessions</option>)}
        </select>
      </label>
      <label className="mm-check"><input type="checkbox" checked={paired} disabled={busy || Boolean(pending.current)} onChange={(event) => setPaired(event.target.checked)} />Compare with an independent directional call</label>
      <p>{paired ? 'Two model runs, using the same captured evidence. Each answer remains hidden from the other.' : 'One model run. Tracking uses completed daily candles and no further model calls.'}</p>
      <label>Price tracking
        <select className="tw-input" value={tracking} disabled={busy || Boolean(pending.current)} onChange={(event) => { trackingTouched.current = true; setTracking(event.target.value); setPreview(null); }}>
          <option value="new">Weekdays · 5 PM New York · {symbol} only</option>
          {eligible.map((scan) => <option value={scan.id} key={scan.id}>{scan.name} · {scan.times.join(', ')}</option>)}
          <option value="paused">Set up tracking later</option>
        </select>
      </label>
      {tracking === 'new' && <p>The scope preview includes any benchmark data needed by the price scan. Only {symbol} receives a forecast.</p>}
      {tracking === 'paused' && <p>Saved forecasts remain marked tracking paused until a price schedule is linked.</p>}
      {preview && <div className="cf-scope"><strong>Acquisition scope</strong><p>{preview.resolvedSymbols.join(', ')}{preview.contextSymbols.length ? ` · context: ${preview.contextSymbols.join(', ')}` : ''}</p>
        <p>Weekdays at 17:00 America/New_York, while the host and scheduler are running.</p>
        {preview.issues.map((issue) => <p role="alert" key={issue}>{issue}</p>)}
      </div>}
      <p>Simulated trades · gross price returns · no broker orders. Account data is excluded. Daily bars can leave the sequence of price touches ambiguous.</p>
      {error && <p className="mm-monitor-error" role="alert">{error}</p>}
      <footer><button className="tw-btn" type="button" onClick={onClose}>Close</button><button className="tw-btn tw-btn--accent" type="submit" disabled={busy || !conversation.model || Boolean(preview?.issues.length)}>
        {busy ? 'Working…' : pending.current ? 'Retry same request' : tracking === 'new' && !preview ? 'Review tracking scope' : 'Record forecast'}</button></footer>
    </form>
  </MonitoringSheet>;
}
