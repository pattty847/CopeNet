import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Bell } from 'lucide-react';
import { wsClient } from '../../../lib/wsClient';
import { AlertEditor } from './AlertEditor';
import { MonitoringSheet } from './MonitoringSheet';
import { conditionLabel, newAlert, timeLabel } from './model';
import { useMonitoring } from './useMonitoring';
import type { AlertRule } from './types';

const MonitorContext = createContext<{
  symbol: string; timeframe: 'daily' | 'weekly' | 'monthly'; rules: AlertRule[] | null;
  error: string; reload: () => Promise<void>;
} | null>(null);

export function TickerMonitorProvider({ symbol, timeframe, children }: {
  symbol: string; timeframe: 'daily' | 'weekly' | 'monthly'; children: ReactNode;
}) {
  const [snapshot, setSnapshot] = useState<{ symbol: string; rules: AlertRule[] } | null>(null);
  const [error, setError] = useState('');
  const sequence = useRef(0);
  const reload = useCallback(async () => {
    const request = ++sequence.current;
    try { const result = await wsClient.marketMonitoring.tickerAlerts(symbol); if (request !== sequence.current) return; setSnapshot({ symbol, rules: result.alerts }); setError(''); }
    catch (reason) { if (request !== sequence.current) return; setError(reason instanceof Error ? reason.message : String(reason)); }
  }, [symbol]);
  useEffect(() => {
    void reload();
    const timer = window.setInterval(() => { if (document.visibilityState === 'visible') void reload(); }, 30000);
    return () => { sequence.current++; window.clearInterval(timer); };
  }, [reload]);
  return <MonitorContext.Provider value={{ symbol, timeframe, rules: snapshot?.symbol === symbol ? snapshot.rules : null, error, reload }}>{children}</MonitorContext.Provider>;
}

export function useTickerMonitorRefresh() { return useContext(MonitorContext)?.reload; }

function TickerMonitorEditor({ rule, onClose }: { rule: AlertRule; onClose: () => void }) {
  const context = useContext(MonitorContext)!;
  const { scans, notifications, catalogue, error, reload } = useMonitoring();
  if (!scans || !notifications || !catalogue.length) return <MonitoringSheet title="Monitor" onClose={onClose}>
    <div className="mm-monitor-form"><p role={error ? 'alert' : 'status'}>{error || 'Loading monitor settings…'}</p>
      <button className="tw-btn" onClick={() => void reload()}>Retry</button></div>
  </MonitoringSheet>;
  const initial = rule.scanId ? rule : { ...rule, scanId: scans.scans.find((scan) => scan.enabled && scan.sources.includes('prices') && scan.resolvedSymbols.includes(context.symbol))?.id ?? '' };
  return <AlertEditor initial={initial} scans={scans} notifications={notifications} catalogue={catalogue} onClose={onClose} onSaved={context.reload} />;
}

export function TickerMonitorPanel() {
  const context = useContext(MonitorContext);
  const [editing, setEditing] = useState<AlertRule | null>(null);
  if (!context) return null;
  const { rules, symbol, timeframe, error, reload } = context;
  return <section className="mm-monitor-form">
    <div className="mm-monitor-row-head"><b>Monitors</b><button className="tw-btn" onClick={() => setEditing({ ...newAlert(symbol), timeframe })}>Add monitor</button></div>
    {error && <p className="mm-monitor-error" role="alert">{error} <button className="tw-btn" onClick={() => void reload()}>Retry</button></p>}
    {!rules && !error && <p role="status">Loading monitors…</p>}
    {rules?.length === 0 && <p>No monitors for {symbol}.</p>}
    {rules?.map((rule) => <div key={rule.alertId} className="mm-monitor-log">
      <div className="mm-monitor-row-head"><button className="mm-monitor-name" onClick={() => setEditing(rule)}>{rule.timeframe} · {conditionLabel(rule)}</button><span>{rule.status.replaceAll('_', ' ')}</span></div>
      <small>Last checked {rule.lastEvaluatedAt ? timeLabel(rule.lastEvaluatedAt) : 'not yet'} · {rule.destinationIds.length ? rule.telegramAuthorized ? 'Telegram authorized' : 'Telegram awaits approval' : 'No Telegram destination'}</small>
      {rule.error && <p>{rule.error}</p>}
    </div>)}
    <small>Monitors use their saved indicator settings. Chart setting changes do not edit a monitor.</small>
    {editing && <TickerMonitorEditor rule={editing} onClose={() => setEditing(null)} />}
  </section>;
}

export function TickerMonitorButton() {
  const context = useContext(MonitorContext);
  const [open, setOpen] = useState(false);
  if (!context) return null;
  const enabled = context.rules?.filter((rule) => rule.enabled) ?? [];
  const pending = enabled.some((rule) => rule.status === 'waiting_confirmation');
  return <>
    <button className="tw-monitor-chip" type="button" onClick={() => setOpen(true)} title="View saved chart monitors">
      <Bell size={12} /> {pending ? 'Awaiting close' : enabled.length ? `Monitoring · ${enabled.length}` : 'Monitor'}
    </button>
    {open && <MonitoringSheet title={`${context.symbol} monitors`} onClose={() => setOpen(false)}><TickerMonitorPanel /></MonitoringSheet>}
  </>;
}
