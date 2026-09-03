import { useEffect, useState } from 'react';
import { wsClient } from '../../../lib/wsClient';
import { MonitoringSheet } from './MonitoringSheet';
import { timeLabel } from './model';
import type { ScanRun } from './types';

export function ScanRunDetails({ summary, onClose }: { summary: ScanRun; onClose: () => void }) {
  const [run, setRun] = useState<ScanRun | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    wsClient.marketMonitoring
      .scanRun(summary.id)
      .then((result) => {
        if (alive) setRun(result.run);
      })
      .catch((reason: unknown) => {
        if (alive) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      alive = false;
    };
  }, [summary.id]);
  return (
    <MonitoringSheet title={summary.name ?? 'Scan results'} onClose={onClose}>
      <div className="mm-monitor-form">
        <div className="mm-monitor-readback">
          <b>{summary.status}</b>
          <span>{timeLabel(summary.startedAt)}</span>
          <small>{summary.resolvedSymbols?.join(', ')}</small>
        </div>
        {error && (
          <p role="alert" className="mm-monitor-error">
            {error}
          </p>
        )}
        {!run && !error && <p>Loading saved source results…</p>}
        {run && (
          <>
            <p>
              {run.cacheHits ?? 0} cached jobs · {run.fetched ?? 0} acquired jobs
            </p>
            {run.errors?.map((item) => (
              <p className="mm-monitor-error" key={item.source + item.symbol}>
                {item.symbol} · {item.source}: {item.message}
              </p>
            ))}
            {run.results?.map((result) => (
              <details key={result.source + result.symbol}>
                <summary>
                  {result.symbol} · {result.source} · {result.cached ? 'cached' : 'acquired'}
                </summary>
                <p>
                  {timeLabel(result.updatedAt)}
                  {result.bars ? ` · ${result.bars} daily bars` : ''}
                </p>
                {result.payload != null && <pre className="mm-monitor-json">{JSON.stringify(result.payload, null, 2)}</pre>}
              </details>
            ))}
            {!!run.screens?.length && (
              <details>
                <summary>Technical screen results · {run.screens.length} assets</summary>
                <pre className="mm-monitor-json">{JSON.stringify(run.screens, null, 2)}</pre>
              </details>
            )}
          </>
        )}
      </div>
    </MonitoringSheet>
  );
}
