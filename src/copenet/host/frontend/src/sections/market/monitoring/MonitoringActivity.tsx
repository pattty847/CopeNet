import type { AlertEvent, NotificationsState, ScanRun } from './types';
import { timeLabel } from './model';
import { useState } from 'react';
import { ScanRunDetails } from './ScanRunDetails';

export function MonitoringActivity({
  runs,
  events,
  notifications,
  busy,
  onAction,
  onTest,
}: {
  runs: ScanRun[];
  events: AlertEvent[];
  notifications: NotificationsState;
  busy: boolean;
  onAction: (id: string, action: 'approve' | 'retry' | 'cancel', uncertain: boolean) => void;
  onTest: (id: string) => void;
}) {
  const [selectedRun, setSelectedRun] = useState<ScanRun | null>(null);
  return (
    <div className="mm-monitor-activity">
      <section>
        <h3>Scan runs</h3>
        {!runs.length && <p className="mm-monitor-empty">No scans have run yet.</p>}
        {runs.map((run) => (
          <div key={run.id} className="mm-monitor-log">
            <div className="mm-monitor-row-head">
              <button className="mm-monitor-name" onClick={() => setSelectedRun(run)}>
                {run.name ?? run.scanId}
              </button>
              <span>{run.status}</span>
              <time>{timeLabel(run.startedAt)}</time>
            </div>
            <p>
              {run.sources?.join(' · ')} · {run.resolvedSymbols?.length ?? 0} assets
            </p>
            <button className="tw-btn" onClick={() => setSelectedRun(run)}>
              Inspect results
            </button>
          </div>
        ))}
      </section>
      <section>
        <h3>Alert events</h3>
        {!events.length && <p className="mm-monitor-empty">No crossings yet. Armed rules establish a baseline first.</p>}
        {events.map((event) => (
          <details key={event.eventId} className="mm-monitor-log">
            <summary>
              <b>
                {event.symbol} · {event.timeframe}
              </b>
              <span>{event.condition}</span>
              <time>{timeLabel(event.evaluatedAt)}</time>
            </summary>
            <p>
              Observed {event.leftValue} vs {event.rightValue}
            </p>
            <p>
              Candle close {timeLabel(event.candleCloseAt)} · Scan {event.scanId}
            </p>
          </details>
        ))}
      </section>
      <section>
        <h3>Telegram delivery</h3>
        {notifications.destinations.map((destination) => (
          <div className="mm-monitor-evidence" key={destination.id}>
            <span>
              {destination.displayName} · {destination.status}
            </span>
            <button
              className="tw-btn"
              disabled={busy || !notifications.transportConfigured || destination.status !== 'configured'}
              onClick={() => onTest(destination.id)}
            >
              Send test message
            </button>
          </div>
        ))}
        {!notifications.deliveries.length && <p className="mm-monitor-empty">No delivery attempts.</p>}
        {notifications.deliveries.map((delivery) => (
          <div className="mm-monitor-log" key={delivery.id}>
            <div className="mm-monitor-row-head">
              <b>
                {notifications.destinations.find((item) => item.id === delivery.destinationId)?.displayName ?? 'Destination unavailable'}
              </b>
              <span>{delivery.status}</span>
              <time>{timeLabel(delivery.createdAt)}</time>
            </div>
            {delivery.error && <p className="mm-monitor-error">{delivery.error}</p>}
            <div className="mm-monitor-actions">
              {delivery.status === 'approval_required' && (
                <button className="tw-btn" disabled={busy} onClick={() => onAction(delivery.id, 'approve', false)}>
                  Approve & send
                </button>
              )}
              {['failed', 'uncertain'].includes(delivery.status) && (
                <button className="tw-btn" disabled={busy} onClick={() => onAction(delivery.id, 'retry', delivery.status === 'uncertain')}>
                  Retry{delivery.status === 'uncertain' ? ' · may duplicate' : ''}
                </button>
              )}
              {['queued', 'approval_required', 'failed', 'uncertain'].includes(delivery.status) && (
                <button className="tw-btn" disabled={busy} onClick={() => onAction(delivery.id, 'cancel', false)}>
                  Cancel delivery
                </button>
              )}
            </div>
          </div>
        ))}
      </section>
      {selectedRun && <ScanRunDetails summary={selectedRun} onClose={() => setSelectedRun(null)} />}
    </div>
  );
}
