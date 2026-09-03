import { useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { AlertEditor } from './AlertEditor';
import { MonitoringActivity } from './MonitoringActivity';
import { MonitoringSheet } from './MonitoringSheet';
import { ScanEditor, ScanScope } from './ScanEditor';
import { conditionLabel, newAlert, newScan, timeLabel } from './model';
import type { AlertRule, Scan, ScanDefinition, ScanPreview } from './types';
import { useMonitoring } from './useMonitoring';
import './monitoring.css';

type Panel = 'scans' | 'alerts' | 'activity';
export function MonitoringSection() {
  const { scans, alerts, catalogue, notifications, error, reload } = useMonitoring();
  const [panel, setPanel] = useState<Panel>(() => {
    const value = new URLSearchParams(window.location.search).get('panel');
    return value === 'alerts' || value === 'activity' ? value : 'scans';
  });
  const [scanEditor, setScanEditor] = useState<ScanDefinition | null>(null);
  const [alertEditor, setAlertEditor] = useState<AlertRule | null>(null);
  const [runPreview, setRunPreview] = useState<{ scan: Scan; preview: ScanPreview } | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const act = async (action: () => Promise<unknown>, message = '') => {
    setBusy(true);
    setActionError('');
    setNotice('');
    try {
      await action();
      await reload();
      setNotice(message);
    } catch (reason) {
      setActionError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  const select = (next: Panel) => {
    setPanel(next);
    const url = new URL(window.location.href);
    url.searchParams.set('panel', next);
    window.history.replaceState({}, '', url);
  };
  const reviewRun = (scan: Scan) =>
    void act(async () => setRunPreview({ scan, preview: await wsClient.marketMonitoring.previewScan(scan) }));
  return (
    <div className="mm-monitor">
      <header className="mm-monitor-heading">
        <div>
          <h2>Scans & alerts</h2>
          <p>Control the scope. Know the next run.</p>
        </div>
        <div className="mm-monitor-next">
          <span>{scans?.schedulerEnabled ? 'Next scheduled scan' : scans ? 'Scheduler paused' : 'Loading schedule'}</span>
          <b>{timeLabel(scans?.nextRunAt)}</b>
          <small>{scans?.scans.find((scan) => scan.id === scans.nextScanId)?.name}</small>
        </div>
      </header>
      <nav className="mm-monitor-toolbar" aria-label="Monitoring views">
        <div>
          {(['scans', 'alerts', 'activity'] as const).map((item) => (
            <button
              className="tw-btn"
              key={item}
              aria-current={panel === item ? 'page' : undefined}
              data-active={panel === item}
              onClick={() => select(item)}
            >
              {item === 'scans'
                ? `Scans${scans ? ` · ${scans.scans.length}` : ''}`
                : item === 'alerts'
                  ? `Alerts${alerts ? ` · ${alerts.alerts.filter((rule) => rule.enabled).length}` : ''}`
                  : 'Activity'}
            </button>
          ))}
        </div>
        <div>
          {panel === 'scans' && (
            <button className="tw-btn" data-active disabled={!scans || busy} onClick={() => setScanEditor(newScan())}>
              + New scan
            </button>
          )}
          {panel === 'alerts' && (
            <button
              className="tw-btn"
              data-active
              disabled={!scans || !notifications || !catalogue.length || busy}
              onClick={() => setAlertEditor(newAlert())}
            >
              + New alert
            </button>
          )}
          <button className="tw-btn" onClick={() => void reload()} disabled={busy}>
            Reload status
          </button>
        </div>
      </nav>
      {(error || actionError) && (
        <p role="alert" className="mm-monitor-error">
          {actionError || error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {panel === 'scans' &&
        (!scans ? (
          <p className="mm-monitor-empty">{error ? 'Scan configuration unavailable. Reload to try again.' : 'Loading scans…'}</p>
        ) : (
          <>
            <div className="mm-monitor-table">
              <div className="mm-monitor-table-head">
                <span>Scan / scope</span>
                <span>Sources</span>
                <span>Schedule</span>
                <span>Last run / actions</span>
              </div>
              {!scans.scans.length && <p className="mm-monitor-empty">No scans. Create a small asset basket to begin.</p>}
              {scans.scans.map((scan) => (
                <article className="mm-monitor-scan" key={scan.id}>
                  <div>
                    <button className="mm-monitor-name" onClick={() => setScanEditor(scan)}>
                      {scan.name}
                    </button>
                    <p>
                      {scan.resolvedSymbols.length} assets{scan.contextSymbols.length ? ` + ${scan.contextSymbols.length} context` : ''} ·{' '}
                      {scan.enabled ? 'Scheduled' : 'Paused'}
                    </p>
                    <details>
                      <summary>Included assets</summary>
                      <p>{scan.resolvedSymbols.join(', ') || 'No assets'}</p>
                      {scan.contextSymbols.length > 0 && <p>Context: {scan.contextSymbols.join(', ')}</p>}
                    </details>
                    {scan.issues.map((issue) => (
                      <p key={issue} className="mm-monitor-error">
                        {issue}
                      </p>
                    ))}
                  </div>
                  <div>
                    <span>{scan.sources.map((id) => scans.sources.find((source) => source.id === id)?.label ?? id).join(' · ')}</span>
                    {scan.publishBrief && <p>Market briefing</p>}
                  </div>
                  <div>
                    <b>{scan.times.join(' / ')}</b>
                    <p>{scan.timezone}</p>
                    <p>{scan.days.length === 7 ? 'Every day' : scan.days.map((day) => ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][day]).join(' · ')}</p>
                    <small>{timeLabel(scan.nextRunAt, scan.timezone)}</small>
                  </div>
                  <div>
                    <span>{scan.lastRun?.status ?? 'Not run yet'}</span>
                    <div className="mm-monitor-actions">
                      <button className="tw-btn" disabled={busy} onClick={() => reviewRun(scan)}>
                        Run now…
                      </button>
                      <button
                        className="tw-btn"
                        disabled={busy}
                        onClick={() => void act(() => wsClient.marketMonitoring.saveScan({ ...scan, enabled: !scan.enabled }))}
                      >
                        {scan.enabled ? 'Pause' : 'Resume'}
                      </button>
                      <button className="tw-btn" disabled={busy} onClick={() => setScanEditor(scan)}>
                        Edit
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
            <p className="mm-monitor-note">
              09:45 defaults to New York time. Missed schedules are skipped; loading Market never starts a scan.
            </p>
          </>
        ))}
      {panel === 'alerts' &&
        (!alerts ? (
          <p className="mm-monitor-empty">{error ? 'Alert state unavailable.' : 'Loading alerts…'}</p>
        ) : (
          <>
            {!alerts.alerts.length && (
              <p className="mm-monitor-empty">No technical alerts. Choose a symbol, a D/W/M condition and the scan that evaluates it.</p>
            )}
            {alerts.alerts.map((rule) => (
              <article className="mm-monitor-alert" key={rule.alertId}>
                <div>
                  <button className="mm-monitor-name" onClick={() => setAlertEditor(rule)}>
                    {rule.symbol} <small>{rule.timeframe}</small>
                  </button>
                  <p>{conditionLabel(rule)}</p>
                  <small>
                    {scans?.scans.find((scan) => scan.id === rule.scanId)?.name ?? 'Scan unavailable'} ·{' '}
                    {rule.oneShot ? 'One-shot' : 'Repeating'} · {rule.destinationIds.length ? 'Pulse + Telegram' : 'Pulse'}
                  </small>
                </div>
                <div>
                  <b>{rule.status.replaceAll('_', ' ')}</b>
                  <p>Last evaluation: {rule.lastEvaluatedAt ? timeLabel(rule.lastEvaluatedAt) : 'Awaiting completed candle'}</p>
                  {rule.observation && <small>{rule.observation.left.toLocaleString()} vs {rule.observation.right.toLocaleString()} · Close {timeLabel(rule.observation.candleCloseAt)}</small>}
                  {rule.error && <p className="mm-monitor-error">{rule.error}</p>}
                </div>
                <div className="mm-monitor-actions">
                  <button className="tw-btn" disabled={busy} onClick={() => setAlertEditor(rule)}>
                    Edit
                  </button>
                  {rule.status !== 'cancelled' && (
                    <button
                      className="tw-btn"
                      disabled={busy}
                      onClick={() => void act(() => wsClient.marketMonitoring.saveAlert({ ...rule, enabled: !rule.enabled }))}
                    >
                      {rule.enabled ? 'Pause' : 'Re-arm'}
                    </button>
                  )}
                  <button
                    className="tw-btn"
                    disabled={busy || rule.status === 'cancelled'}
                    onClick={() => void act(() => wsClient.marketMonitoring.cancelAlert(rule.alertId))}
                  >
                    Cancel
                  </button>
                </div>
              </article>
            ))}
            <p className="mm-monitor-note">D/W/M only · chart indicator calculations · completed candles · no intraday polling</p>
          </>
        ))}
      {panel === 'activity' &&
        (notifications ? (
          <MonitoringActivity
            runs={scans?.runs ?? []}
            events={alerts?.events ?? []}
            notifications={notifications}
            busy={busy}
            onTest={(id) => {
              if (window.confirm('Send a real test message to this Telegram destination?'))
                void act(() => wsClient.marketMonitoring.testDestination(id), 'Test request recorded. Check delivery status below.');
            }}
            onAction={(id, action, uncertain) => {
              if (!uncertain || window.confirm('Telegram may already have received this message. Retry and risk a duplicate?'))
                void act(() => wsClient.marketMonitoring.deliveryAction(id, action, uncertain));
            }}
          />
        ) : (
          <p className="mm-monitor-empty">{error ? 'Delivery state unavailable.' : 'Loading activity…'}</p>
        ))}
      {scanEditor && scans && <ScanEditor initial={scanEditor} state={scans} onClose={() => setScanEditor(null)} onSaved={reload} />}
      {alertEditor && scans && notifications && (
        <AlertEditor
          initial={alertEditor}
          scans={scans}
          catalogue={catalogue}
          notifications={notifications}
          onClose={() => setAlertEditor(null)}
          onSaved={reload}
        />
      )}
      {runPreview && (
        <MonitoringSheet title={`Run ${runPreview.scan.name}`} onClose={() => setRunPreview(null)}>
          <div className="mm-monitor-form">
            <ScanScope preview={runPreview.preview} />
            <p>This action may contact the selected data providers. Cached work is reused where possible.</p>
            {actionError && (
              <p role="alert" className="mm-monitor-error">
                {actionError}
              </p>
            )}
            <footer>
              <button className="tw-btn" onClick={() => setRunPreview(null)}>
                Cancel
              </button>
              <button
                className="tw-btn"
                data-active
                disabled={busy || !!runPreview.preview.issues.length}
                onClick={() =>
                  void act(async () => {
                    await wsClient.marketMonitoring.runScan(runPreview.scan.id, runPreview.preview.scopeToken);
                    setRunPreview(null);
                  }, 'Scan started. Follow its progress in Activity.')
                }
              >
                {busy ? 'Starting…' : 'Run this scan'}
              </button>
            </footer>
          </div>
        </MonitoringSheet>
      )}
    </div>
  );
}
