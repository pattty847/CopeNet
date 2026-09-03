import { useState, type FormEvent } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { AlertOperandEditor } from './AlertOperandEditor';
import { MonitoringSheet } from './MonitoringSheet';
import { conditionLabel, toggleValue } from './model';
import type { AlertRule, IndicatorOption, NotificationsState, ScansState } from './types';

export function AlertEditor({
  initial,
  scans,
  catalogue,
  notifications,
  onClose,
  onSaved,
}: {
  initial: AlertRule;
  scans: ScansState;
  catalogue: IndicatorOption[];
  notifications: NotificationsState;
  onClose: () => void;
  onSaved: () => Promise<void>;
}) {
  const [rule, setRule] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const update = (change: Partial<AlertRule>) => setRule({ ...rule, ...change });
  const scan = scans.scans.find((item) => item.id === rule.scanId);
  const save = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      await wsClient.marketMonitoring.saveAlert(rule);
      await onSaved();
      onClose();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setBusy(false);
    }
  };
  return (
    <MonitoringSheet title={initial.alertId ? 'Edit alert' : 'New technical alert'} onClose={onClose}>
      <form className="mm-monitor-form" onSubmit={(event) => void save(event)}>
        <div className="mm-monitor-fields">
          <label>
            Symbol
            <input
              className="tw-input"
              autoFocus
              required
              value={rule.symbol}
              onChange={(event) => update({ symbol: event.target.value.toUpperCase().trim() })}
              placeholder="AAPL"
            />
          </label>
          <label>
            Timeframe
            <select
              aria-label="Timeframe"
              className="tw-input"
              value={rule.timeframe}
              onChange={(event) => update({ timeframe: event.target.value as AlertRule['timeframe'] })}
            >
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
        </div>
        <label>
          Evaluate after scan
          <select
            aria-label="Evaluate after scan"
            className="tw-input"
            required
            value={rule.scanId}
            onChange={(event) => update({ scanId: event.target.value })}
          >
            <option value="">Choose a price scan</option>
            {scans.scans
              .filter((item) => item.sources.includes('prices'))
              .map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                  {!item.enabled ? ' · paused' : ''}
                </option>
              ))}
          </select>
        </label>
        {scan && !scan.resolvedSymbols.includes(rule.symbol) && (
          <p className="mm-monitor-error">
            Add {rule.symbol || 'this symbol'} to {scan.name} before saving this alert.
          </p>
        )}
        <div className="mm-monitor-fields mm-monitor-operands">
          <AlertOperandEditor label="Observe" operand={rule.left} catalogue={catalogue} onChange={(left) => update({ left })} />
          <AlertOperandEditor label="Compare with" operand={rule.right} catalogue={catalogue} onChange={(right) => update({ right })} />
        </div>
        <label>
          Condition
          <select
            className="tw-input"
            value={rule.direction}
            onChange={(event) => update({ direction: event.target.value as AlertRule['direction'] })}
          >
            <option value="above">Crosses above</option>
            <option value="below">Crosses below</option>
          </select>
        </label>
        <div className="mm-monitor-readback">
          <b>
            {rule.symbol || 'Symbol'} · {rule.timeframe}
          </b>
          <span>{conditionLabel(rule)}</span>
          <small>Completed candles only. Arming establishes a baseline; it never reports an old crossing.</small>
        </div>
        <label className="mm-check">
          <input type="checkbox" checked={rule.oneShot} onChange={(event) => update({ oneShot: event.target.checked })} /> One-shot · stop
          after the first crossing
        </label>
        {!rule.oneShot && <p>Repeating alerts re-arm only after the condition resets.</p>}
        <fieldset>
          <legend>Delivery</legend>
          <p>Every crossing is recorded here and in Pulse.</p>
          {!notifications.transportConfigured && (
            <p className="mm-monitor-error">Telegram is not configured. Configure the bot in Messaging to enable delivery.</p>
          )}
          {notifications.destinations.length === 0 && <p>No Telegram destinations. Add one in Messaging settings.</p>}
          {notifications.destinations.map((destination) => (
            <label className="mm-check" key={destination.id}>
              <input
                type="checkbox"
                checked={rule.destinationIds.includes(destination.id)}
                onChange={() => update({ destinationIds: toggleValue(rule.destinationIds, destination.id) })}
              />
              {destination.displayName}
              <span>{destination.status}</span>
            </label>
          ))}
          {rule.destinationIds.length > 0 && (
            <label className="mm-check">
              <input
                type="checkbox"
                checked={rule.telegramAuthorized}
                onChange={(event) => update({ telegramAuthorized: event.target.checked })}
              />{' '}
              Automatically send this rule’s alerts to these destinations
            </label>
          )}
          {rule.destinationIds.length > 0 && !rule.telegramAuthorized && <p>Delivery waits for your approval in Activity.</p>}
        </fieldset>
        {error && (
          <p className="mm-monitor-error" role="alert">
            {error}
          </p>
        )}
        <footer>
          <button className="tw-btn" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="tw-btn" data-active disabled={busy}>
            {busy ? 'Saving…' : initial.alertId ? 'Save alert' : 'Arm alert'}
          </button>
        </footer>
      </form>
    </MonitoringSheet>
  );
}
